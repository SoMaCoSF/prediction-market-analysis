# file_id: SOM-PY-0918-v1.0.0 name: sb.py description: Supabase PG connection helper — reads .env_turso (gitignored), returns psycopg2 conn to the cloud trading-ledger SoT. NEVER prints secrets. project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [supabase, postgres, ledger, cloud] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
"""sb.py — Supabase cloud Postgres connection (trading-ledger source of truth).

Local PG keeps the 52.77M-row analytics corpus; Supabase holds the small,
shared trading ledger (uuid_orders/fills/positions/marks) so BOTH the local
mission control and the Vercel deployment read/write ONE ledger. Native PG
bigint pairs keep the 128-bit bitmask routing intact (impossible on Turso).
"""
from __future__ import annotations

from pathlib import Path

ENV_FILE = Path(__file__).resolve().parent.parent / ".env_turso"


def _load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or "=" not in line or line.startswith("#"):
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def supabase_dsn() -> str:
    """Build the Supabase PG URI from gitignored env parts (never printed)."""
    env = _load_env()
    ref = env.get("SUPABASE_REF", "")
    pw = env.get("SUPABASE_DB_PASSWORD", "")
    if not (ref and pw):
        raise RuntimeError("SUPABASE_REF / SUPABASE_DB_PASSWORD missing in .env_turso")
    return f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"


def sb_conn():
    import psycopg2
    # statement_timeout: a blocked write aborts after 30s instead of hanging a daemon forever
    return psycopg2.connect(supabase_dsn(), connect_timeout=15,
                            options="-c statement_timeout=30000")


def status_salt() -> str:
    return _load_env().get("STATUS_SALT", "somacosf-2026")


if __name__ == "__main__":
    # connectivity self-test: prints only non-secret facts
    try:
        con = sb_conn()
        cur = con.cursor()
        cur.execute("SELECT current_database(), version()")
        db, ver = cur.fetchone()
        print("SB OK:", db, "|", ver.split(",")[0])
        con.close()
    except Exception as e:
        print("SB FAIL:", repr(e)[:200])
