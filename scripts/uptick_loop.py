#!/usr/bin/env python3
"""/loop UPTICK monitor — runs autonomously, never trades.

Each tick it:
  1. Scouts Kalshi PUBLIC market catalog for REAL liquidity (vol24h>0 AND two-sided spread)
  2. Reads auth'd balance + open positions (read-only)
  3. Writes data/uptick_status.json + appends a compact line to data/uptick.log
  4. Prints a one-line status for cron capture

Discipline: NEVER places orders. Only reports. Arms a flag in status when
real liquidity appears so a human (or a GO-gated trader) can act.

Run: .venv311/Scripts/python scripts/uptick_loop.py
"""
import base64, json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

KALSHI_HOST = os.getenv("KALSHI_HOST", "https://api.elections.kalshi.com/trade-api/v2")
PUBLIC = "https://api.elections.kalshi.com/trade-api/v2/markets"
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
STATUS_FILE = DATA / "uptick_status.json"
LOG_FILE = DATA / "uptick.log"

FLOOR = 10.00  # cash floor — never trade below this


def keys():
    kid = os.getenv("KALSHI_KEY_ID")
    kpath = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    if not kpath and (ROOT / ".kalshi_key.pem").exists():
        kpath = str(ROOT / ".kalshi_key.pem")
    return kid, kpath


def sign(method, path, ts):
    _, kpath = keys()
    key = serialization.load_pem_private_key(Path(kpath).read_bytes(), password=None)
    full = "/trade-api/v2" + path.split("?")[0]
    msg = f"{ts}{method.upper()}{full}".encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return base64.b64encode(sig).decode()


def kalshi_get(path):
    kid, _ = keys()
    ts = str(int(time.time() * 1000))
    headers = {
        "KALSHI-ACCESS-KEY": kid,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sign("GET", path, ts),
    }
    r = httpx.get(KALSHI_HOST + path, headers=headers, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"Kalshi {r.status_code}: {r.text[:160]}")
    return r.json()


def scout_liquidity(limit=200):
    out, cursor = [], None
    while len(out) < limit:
        url = f"{PUBLIC}?status=open&limit=100"
        if cursor:
            url += f"&cursor={cursor}"
        r = httpx.get(url, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"Public {r.status_code}")
        j = r.json()
        batch = j.get("markets", [])
        if not batch:
            break
        out.extend(batch)
        cursor = j.get("cursor")
        if not cursor:
            break
    liquid = []
    for m in out:
        vol = float(m.get("volume_24h") or 0)
        if vol <= 0:
            continue
        yb, ya = float(m.get("yes_bid", 0) or 0), float(m.get("yes_ask", 0) or 0)
        nb, na = float(m.get("no_bid", 0) or 0), float(m.get("no_ask", 0) or 0)
        if (yb > 0 and ya > 0) or (nb > 0 and na > 0):
            liquid.append({
                "ticker": m.get("ticker"),
                "title": (m.get("title") or "")[:50],
                "vol24": vol,
                "yes_bid": yb, "yes_ask": ya,
                "no_bid": nb, "no_ask": na,
            })
    liquid.sort(key=lambda x: x["vol24"], reverse=True)
    return len(out), liquid


def main():
    now = datetime.now(timezone.utc).isoformat()
    status = {"ts": now, "auth_ok": False, "cash": None, "portfolio_value": None,
              "positions": None, "open_markets": None, "liquid_markets": 0,
              "armed": False, "top": [], "note": ""}
    try:
        bal = kalshi_get("/portfolio/balance")
        cash = float(bal.get("balance_dollars", 0) or 0)
        pv = float(bal.get("portfolio_value", 0) or 0)
        status["cash"] = cash
        status["portfolio_value"] = pv
        status["auth_ok"] = True
        pos = kalshi_get("/portfolio/positions?status=open&limit=200")
        status["positions"] = len(pos.get("positions", []))
    except Exception as e:
        status["note"] = f"balance read failed: {e}"

    try:
        total, liquid = scout_liquidity()
        status["open_markets"] = total
        status["liquid_markets"] = len(liquid)
        status["top"] = liquid[:5]
        status["armed"] = len(liquid) > 0 and (status["cash"] or 0) > FLOOR
    except Exception as e:
        status["note"] = (status["note"] + f" | scout failed: {e}").strip(" |")

    if not status["armed"]:
        if status.get("liquid_markets", 0) == 0:
            status["note"] = (status["note"] + " | VENUE DEAD: 0 two-sided volume — holding at floor, no fee bleed.").strip(" |")
        elif (status.get("cash") or 0) <= FLOOR:
            status["note"] = (status["note"] + " | cash at/below floor — no auto-trade.").strip(" |")

    # Warm the execution path every tick (DRY_RUN) so it's live-ready the
    # instant liquidity returns. Never posts unless GO_TRADE exists.
    exec_action = "none"
    try:
        from kalshi_executor import execute_once
        ex = execute_once(force_live=False)
        exec_action = ex.get("action", "none")
        status["exec_action"] = exec_action
        status["exec_detail"] = ex.get("detail", "")
        # If the executor WOULD have acted (entry/exit) and venue is armed,
        # that's the signal to surface to the user.
        if exec_action in ("entry", "exit") and status["armed"]:
            status["note"] = (status["note"] + f" | EXECUTOR WOULD {exec_action.upper()} — DRY_RUN (drop GO_TRADE to go live)").strip(" |")
    except Exception as e:
        status["note"] = (status["note"] + f" | executor warm failed: {e}").strip(" |")

    STATUS_FILE.write_text(json.dumps(status, indent=2))
    line = f"{now[:19]}Z cash=${status['cash']} pos={status['positions']} open={status['open_markets']} liquid={status['liquid_markets']} armed={status['armed']} exec={exec_action} {status['note']}"
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")
    print(line)
    return status


if __name__ == "__main__":
    main()
