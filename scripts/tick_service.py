# file_id: SOM-PY-0983-v1.0.0 name: tick_service.py description: In-memory tick service — RAM ring buffers per symbol, sub-ms HTTP reads for engines, batched COPY flush to local Postgres (GIS/vector install); the wire-speed spine; zero tokens project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [tick, in-memory, wirespeed, postgres, flush] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
"""tick_service.py — the in-memory tick plane.

Hot path: WS daemons POST ticks -> RAM ring buffer (deque, 2000/symbol).
Engines GET /tick/<sym>?secs=180 -> latest price + window momentum from RAM
(sub-ms, zero disk). Persistence: every FLUSH_S seconds, batch COPY the
spooled rows to the local Postgres (the GIS/pgvector install) — one writer,
no lock contention. Zero model tokens.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fleetlib  # noqa: E402
import runlog  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
PORT = 8421
RING = 2000
FLUSH_S = 5.0

TICKS: dict[str, deque] = defaultdict(lambda: deque(maxlen=RING))   # sym -> [(ts, price, bid)]
SPOOL: list[tuple] = []                                             # pending pg rows
LOCK = threading.Lock()


def pg_conn():
    import psycopg2
    dsn = os.getenv("LOCAL_PG_DSN") or os.getenv("PG_DSN")
    if not dsn:
        return None
    return psycopg2.connect(dsn, connect_timeout=5,
                            options="-c statement_timeout=10000")


def ensure_table():
    try:
        con = pg_conn()
        if not con:
            return False
        con.autocommit = True
        con.cursor().execute("""
            CREATE TABLE IF NOT EXISTS tick_stream (
                ts BIGINT, source TEXT, symbol TEXT, price_c REAL, bid_c REAL)""")
        con.close()
        return True
    except Exception:
        return False


def flusher():
    while True:
        time.sleep(FLUSH_S)
        fleetlib.checkin("tick")
        with LOCK:
            rows, SPOOL[:] = SPOOL[:], []
        if not rows:
            continue
        try:
            con = pg_conn()
            if not con:
                continue
            cur = con.cursor()
            cur.executemany(
                "INSERT INTO tick_stream (ts, source, symbol, price_c, bid_c) VALUES (%s,%s,%s,%s,%s)", rows)
            con.commit()
            con.close()
        except Exception as e:
            runlog.log_event("tick", f"flush warn {repr(e)[:50]}", kind="warn")


def window_stats(sym, secs):
    now = time.time()
    with LOCK:
        rows = [r for r in TICKS.get(sym, ()) if now - r[0] <= secs]
    if not rows:
        return None
    p0, p1 = rows[0][1], rows[-1][1]
    return {"sym": sym, "n": len(rows), "price": p1, "bid": rows[-1][2],
            "mom_bps": (p1 - p0) / p0 * 10000 if p0 else 0.0,
            "age_ms": round((now - rows[-1][0]) * 1000)}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path == "/tick":
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"[]")
                if isinstance(body, dict):
                    body = [body]
                with LOCK:
                    for t in body:
                        sym = t.get("sym")
                        if not sym:
                            continue
                        row = (float(t.get("ts") or time.time()), float(t.get("price") or 0),
                               float(t.get("bid") or 0))
                        TICKS[sym].append(row)
                        SPOOL.append((int(row[0]), t.get("source", "ws"), sym, row[1], row[2]))
                self._ok({"ok": True, "n": len(body)})
            except Exception as e:
                self._ok({"ok": False, "err": repr(e)[:80]}, 400)
        else:
            self._ok({"err": "unknown"}, 404)

    def do_GET(self):
        if self.path.startswith("/tick/"):
            parts = self.path.split("?")[0].split("/")
            sym = parts[2] if len(parts) > 2 else ""
            secs = 180
            if "secs=" in self.path:
                try:
                    secs = int(self.path.split("secs=")[1].split("&")[0])
                except Exception:
                    pass
            self._ok(window_stats(sym, secs) or {"sym": sym, "n": 0})
        elif self.path == "/health":
            with LOCK:
                snap = {s: len(d) for s, d in TICKS.items()}
            self._ok({"ok": True, "symbols": snap, "spool": len(SPOOL)})
        else:
            self._ok({"err": "unknown"}, 404)

    def _ok(self, obj, code=200):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)


def main():
    fleetlib.acquire_lock("tick")
    pg_ok = ensure_table()
    runlog.log_event("tick", f"tick service start :{PORT} pg={'ok' if pg_ok else 'NO-DSN (ram-only)'}")
    threading.Thread(target=flusher, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()


if __name__ == "__main__":
    sys.exit(main())
