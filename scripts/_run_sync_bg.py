import os, sys
env={}
for line in open(".env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
ref=env["SUPABASE_REF"]; pw=env["SUPABASE_DB_PASSWORD"]
uri=f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"
os.environ["PGCONNECTIONSTRING"]=uri
sys.path.insert(0,"scripts")
from sync_supabase_subset import run
print("[sync] target:", uri.split("@")[1])
run(1_500_000)
print("[sync] complete")
