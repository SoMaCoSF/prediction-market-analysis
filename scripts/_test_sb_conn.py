import psycopg2

env={}
for line in open(".env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
ref=env["SUPABASE_REF"]; pw=env["SUPABASE_DB_PASSWORD"]
uri=f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"
try:
    c=psycopg2.connect(uri, connect_timeout=15)
    cur=c.cursor(); cur.execute("SELECT version();")
    print("CONNECTED OK:", cur.fetchone()[0][:45])
    c.close()
except Exception as e:
    print("CONNECT FAILED:", str(e)[:300])
