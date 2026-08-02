import os, httpx
env = {}
for line in open("D:/somacosf/outputs/prediction-market-analysis/.env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v = line.split("=",1); env[k.strip()]=v.strip()
tok = env["SUPABASE_TOKEN"]; ref = tok[len("sbp_"):]
h = {"Authorization": f"Bearer {tok}", "Content-Type":"application/json"}
for url in [
    f"https://api.supabase.com/v1/projects/{ref}",
    f"https://api.supabase.com/v1/projects/{ref}/api-keys",
    f"https://api.supabase.com/v1/projects/{ref}/database/pooler/connection-string?connection_string_type=uri",
]:
    try:
        r = httpx.get(url, headers=h, timeout=20)
        print("\n==", url, r.status_code)
        print(r.text[:1000])
    except Exception as e:
        print("err", e)
