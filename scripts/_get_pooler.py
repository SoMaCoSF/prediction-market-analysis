# fetch Supabase POOLER connection string via management API (never prints the password)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import httpx
import sb

env = sb._load_env()
tok = env["SUPABASE_TOKEN"]
ref = env["SUPABASE_REF"]
h = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
for url in [
    f"https://api.supabase.com/v1/projects/{ref}/database/pooler/connection-string?connection_string_type=uri",
]:
    r = httpx.get(url, headers=h, timeout=20)
    print("status:", r.status_code)
    txt = r.text
    # redact any embedded password before printing
    pw = env.get("SUPABASE_DB_PASSWORD", "")
    if pw:
        txt = txt.replace(pw, "<PASSWORD>")
    print(txt[:500])
