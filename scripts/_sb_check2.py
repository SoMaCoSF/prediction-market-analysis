import psycopg2

env={}
for line in open(".env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
cs=f"postgresql://postgres:{env['SUPABASE_DB_PASSWORD']}@db.{env['SUPABASE_REF']}.supabase.co:5432/postgres"
try:
    c=psycopg2.connect(cs, connect_timeout=10)
    cur=c.cursor()
    cur.execute("select count(*) from uuid_trades_subset")
    print("OK local->supabase, subset rows =", cur.fetchone()[0])
    c.close()
except Exception as e:
    print("ERR", repr(e))
