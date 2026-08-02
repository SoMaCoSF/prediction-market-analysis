import os, psycopg2
env={}
for line in open(".env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
ref=env["SUPABASE_REF"]; pw=env["SUPABASE_DB_PASSWORD"]
uri=f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"
os.environ["PGCONNECTIONSTRING"]=uri

import sys; sys.path.insert(0, "scripts")
from sync_supabase_subset import ensure_schema, run

print("[1] creating subset schema in Supabase...")
sc=psycopg2.connect(uri, connect_timeout=15)
ensure_schema(sc); sc.close()

print("[2] running sync (latest 1.5M rows local -> Supabase)...")
run(1_500_000)
print("[done]")
