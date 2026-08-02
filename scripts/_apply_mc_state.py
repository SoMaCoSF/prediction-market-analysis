# apply mc_state + mc_log tables to Supabase (serverless control state)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sb

DDL = """
CREATE TABLE IF NOT EXISTS mc_state (
    k TEXT PRIMARY KEY,
    v TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS mc_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts BIGINT NOT NULL,
    kind TEXT NOT NULL,
    msg TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
con = sb.sb_conn()
con.autocommit = True
cur = con.cursor()
cur.execute(DDL)
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'mc_%' ORDER BY 1")
print("mc tables:", [r[0] for r in cur.fetchall()])
con.close()
print("MC STATE TABLES APPLIED")
