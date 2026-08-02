# get project region, construct + TEST pooler connection strings (password never printed)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import psycopg2
import sb

env = sb._load_env()
tok, ref, pw = env["SUPABASE_TOKEN"], env["SUPABASE_REF"], env["SUPABASE_DB_PASSWORD"]
h = {"Authorization": f"Bearer {tok}"}
r = httpx.get(f"https://api.supabase.com/v1/projects/{ref}", headers=h, timeout=20)
region = r.json().get("region") if r.status_code == 200 else None
print("region:", region)

candidates = []
if region:
    candidates = [
        f"postgresql://postgres.{ref}:{pw}@aws-0-{region}.pooler.supabase.com:5432/postgres",
        f"postgresql://postgres.{ref}:{pw}@aws-0-{region}.pooler.supabase.com:6543/postgres",
        f"postgresql://postgres.{ref}:{pw}@aws-1-{region}.pooler.supabase.com:5432/postgres",
    ]
for dsn in candidates:
    host = dsn.split("@")[1].split("/")[0]
    try:
        con = psycopg2.connect(dsn, connect_timeout=10)
        cur = con.cursor()
        cur.execute("SELECT 1")
        print(f"OK   {host}")
        con.close()
    except Exception as e:
        print(f"FAIL {host}  {repr(e)[:80]}")
