# probe_pg.py — check PG connectivity + uuid tables. Scratch probe.
import sys

import psycopg2

try:
    con = psycopg2.connect(
        host="127.0.0.1", port=5432, dbname="postgres",
        user="postgres", password="hermes_pg_2026", connect_timeout=10,
    )
except Exception as e:
    print("CONNECT FAIL:", repr(e)[:300])
    sys.exit(1)

cur = con.cursor()
cur.execute("SELECT version()")
print("VERSION:", cur.fetchone()[0][:60])
cur.execute(
    "SELECT table_name FROM information_schema.tables "
    "WHERE table_schema='public' AND table_name LIKE 'uuid%' ORDER BY 1"
)
tables = [r[0] for r in cur.fetchall()]
print("uuid tables:", tables)
for t in tables:
    cur.execute(f"SELECT count(*) FROM {t}")
    print(f"  {t}: {cur.fetchone()[0]:,}")
con.close()
print("PROBE OK")
