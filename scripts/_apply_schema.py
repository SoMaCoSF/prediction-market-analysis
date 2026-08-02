# apply schema for real (committed), then report tables
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import psycopg2

schema = Path(__file__).resolve().parent.joinpath("ledger_schema.sql").read_text()
con = psycopg2.connect(host="127.0.0.1", port=5432, dbname="postgres",
                       user="postgres", password="hermes_pg_2026", connect_timeout=10)
con.autocommit = True
cur = con.cursor()
cur.execute(schema)
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_name LIKE 'uuid_%' ORDER BY 1")
print("tables:", [r[0] for r in cur.fetchall()])
con.close()
print("SCHEMA APPLIED")
