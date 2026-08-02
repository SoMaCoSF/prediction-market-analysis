import os, httpx
url=os.getenv("TURSO_DATABASE_URL") or os.getenv("TURSO_DB_URL")
token=os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_DB_TOKEN")
base=url.replace("libsql://","https://",1).rstrip("/")
h={"Authorization":f"Bearer {token}","Content-Type":"application/json"}
def run(sql):
    r=httpx.post(f"{base}/v2/pipeline", json={"requests":[{"type":"execute","stmt":{"sql":sql}},{"type":"close"}]}, headers=h, timeout=30)
    return r.status_code, r.text[:600]

print("== sqlite int64 ceiling ==")
print(run("SELECT 1<<62 AS big, (1<<63) AS over"))   # shows sqlite is 64-bit
print("\n== doc claim: (CAST(uuid AS INT) >> 116) & 0xFFF ==")
print(run("SELECT (CAST('3a09bc6b-9a36-8010-8fff-f7efacbba918' AS INTEGER) >> 116) & 0xFFF AS t"))
print("\n== fix: extract type from hex TEXT via substr (first 4 hex chars) ==")
print(run("SELECT substr('3a09bc6b-9a36-8010-8fff-f7efacbba918',1,4) AS tp"))
print("\n== proper 128-bit routing needs an integer column; test bitwise on 64-bit int ==")
print(run("SELECT ((9223372036854775807 >> 60) & 0xFFF) AS t"))
