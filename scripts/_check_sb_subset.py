import os, psycopg2
env={}
for line in open(".env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
uri=f"postgresql://postgres:{env['SUPABASE_DB_PASSWORD']}@db.{env['SUPABASE_REF']}.supabase.co:5432/postgres"
try:
    c=psycopg2.connect(uri,connect_timeout=15)
    cur=c.cursor(); cur.execute("SELECT count(*) FROM uuid_trades_subset;")
    print("subset rows:", cur.fetchone()[0])
    c.close()
except Exception as e:
    print("subset check failed:", str(e)[:160])
