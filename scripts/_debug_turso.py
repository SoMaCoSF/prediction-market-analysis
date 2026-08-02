"""Debug: capture full Turso pipeline error body for a single insert."""
import os, json, httpx
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
url = os.getenv("TURSO_DATABASE_URL") or os.getenv("TURSO_DB_URL")
token = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("TURSO_DB_TOKEN")
base = url.replace("libsql://", "https://", 1).rstrip("/")
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Try a single insert with the exact shape the script uses
row = {
    "uuid": "00000000-0000-8000-8000-000000000001",
    "market_id": "DEBUG_MARKET",
    "venue_id": 200,
    "signal": 1.0,
    "provenance": 7,
    "timestamp": 1700000000,
}
payload = {"requests": [{
    "type": "execute",
    "stmt": {
        "sql": "INSERT INTO uuid_vectors (uuid, market_id, venue_id, signal, provenance, timestamp) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(uuid) DO NOTHING",
        "args": [
            {"type": "text", "value": row["uuid"]},
            {"type": "text", "value": row["market_id"]},
            {"type": "integer", "value": row["venue_id"]},
            {"type": "real", "value": row["signal"]},
            {"type": "integer", "value": row["provenance"]},
            {"type": "integer", "value": row["timestamp"]},
        ],
    },
}]}

print("PAYLOAD:")
print(json.dumps(payload, indent=2))
r = httpx.post(f"{base}/v2/pipeline", json=payload, headers=headers, timeout=30)
print("STATUS:", r.status_code)
print("BODY:")
print(r.text[:2000])
