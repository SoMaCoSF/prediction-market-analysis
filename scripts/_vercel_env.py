import os, subprocess
ROOT = "D:/somacosf/outputs/prediction-market-analysis"
env={}
for line in open(os.path.join(ROOT, ".env_turso")):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
ref=env["SUPABASE_REF"]; pw=env["SUPABASE_DB_PASSWORD"]
uri=f"postgresql://postgres:{pw}@db.{ref}.supabase.co:5432/postgres"
salt=env["STATUS_SALT"]

# set env vars (non-interactive: pipe value to `vercel env add`)
for name, val in [("PG_CONNECTION_STRING", uri), ("STATUS_SALT", salt)]:
    p = subprocess.run(["vercel","env","add",name,"production"],
                       input=val+"\n", capture_output=True, text=True)
    print(f"[{name}] rc={p.returncode} out={p.stdout.strip()[-120:]} err={p.stderr.strip()[-120:]}")

# set production domain
d = subprocess.run(["vercel","domains","add","uuid.somacosf.com"],
                   capture_output=True, text=True)
print(f"[domain] rc={d.returncode} out={d.stdout.strip()[-160:]} err={d.stderr.strip()[-160:]}")