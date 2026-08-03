import httpx

env={}
for line in open("D:/somacosf/outputs/prediction-market-analysis/.env_turso"):
    line=line.strip()
    if not line or "=" not in line: continue
    k,v=line.split("=",1); env[k.strip()]=v.strip()
tok=env["SUPABASE_TOKEN"]; ref="qxxuovjqdknxxzrnlpow"
h={"Authorization":f"Bearer {tok}","Content-Type":"application/json"}
# connection string endpoint
for url in [
    f"https://api.supabase.com/v1/projects/{ref}/database/connection-string?connection_string_type=uri",
    f"https://api.supabase.com/v1/projects/{ref}/database/pooler/connection-string?connection_string_type=uri",
]:
    r=httpx.get(url,headers=h,timeout=20)
    print(url, r.status_code)
    print(r.text[:600])
    print("---")
