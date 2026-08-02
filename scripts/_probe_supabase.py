import os, json, httpx
# Read .env_turso for SUPABASE_TOKEN
env = {}
p = "D:/somacosf/outputs/prediction-market-analysis/.env_turso"
for line in open(p):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v = line.split("=",1)
    env[k.strip()] = v.strip()

tok = env.get("SUPABASE_TOKEN")
if not tok:
    print("NO SUPABASE_TOKEN"); raise SystemExit(1)
ref = tok[len("sbp_"):]
print("project_ref:", ref)
headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
# Try management API endpoints to get connection info / db password
for url in [
    f"https://api.supabase.com/v1/projects/{ref}/database/connection-string",
    f"https://api.supabase.com/v1/projects/{ref}/database",
]:
    try:
        r = httpx.get(url, headers=headers, timeout=20)
        print("\nGET", url, "->", r.status_code)
        print(r.text[:800])
    except Exception as e:
        print("err", url, e)
