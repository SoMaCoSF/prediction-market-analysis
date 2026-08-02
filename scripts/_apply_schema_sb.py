# push ledger_schema.sql to Supabase (idempotent), then list uuid_ tables
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import sb

schema = Path(__file__).resolve().parent.joinpath("ledger_schema.sql").read_text()
con = sb.sb_conn()
con.autocommit = True
cur = con.cursor()
cur.execute(schema)
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'uuid_%' ORDER BY 1")
print("supabase uuid_ tables:", [r[0] for r in cur.fetchall()])
con.close()
print("SB SCHEMA APPLIED")
