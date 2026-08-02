Yes! You don't need libsql-experimental or C++ build tools on Windows at all.

Turso databases are powered by libSQL, which exposes a native HTTP / REST API (hrana protocol). Instead of using native C bindings, you can use pure-Python HTTP libraries like httpx or requests to send SQL queries and batch transactions directly over HTTPS.

Here are the two pure-Python alternatives that bypass native C compilation completely on Windows:

Option 1: turso-http / httpx (Recommended)
You can interact with Turso's REST API directly using httpx. It is lightweight, fast, pure Python, and works on any OS without build tools.

1. Install httpx
Bash
uv add httpx
2. Pure Python Batch Ingest Snippet
Python
import os
import httpx

TURSO_URL = os.getenv("TURSO_DATABASE_URL")  # e.g., "https://your-db-name.turso.io"
TURSO_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Convert libsql:// URL to standard https:// if necessary
if TURSO_URL.startswith("libsql://"):
    TURSO_URL = TURSO_URL.replace("libsql://", "https://")

def execute_pipeline(statements: list[dict]):
    """Execute a batch of SQL statements over HTTP."""
    endpoint = f"{TURSO_URL}/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {TURSO_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # Format requests for Hrana v2 pipeline API
    requests_payload = []
    for stmt in statements:
        requests_payload.append({
            "type": "execute",
            "stmt": stmt
        })

    payload = {"requests": requests_payload}

    response = httpx.post(endpoint, json=payload, headers=headers, timeout=30.0)
    response.raise_for_status()
    return response.json()

# Example: Batch Insert using Parameterized Queries
statements = [
    {
        "sql": "INSERT INTO uuid_vectors (uuid, market_id, venue_id, signal, provenance, timestamp) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(uuid) DO NOTHING",
        "args": [
            {"type": "text", "value": "3a0b986b-a45b-8010-9fff-fda6ed84f3e4"},
            {"type": "text", "value": "POLYM-123"},
            {"type": "integer", "value": 200},
            {"type": "float", "value": 1.0},
            {"type": "integer", "value": 7},
            {"type": "integer", "value": 1700000000}
        ]
    }
]

# Run the request
# execute_pipeline(statements)
Option 2: Run via Node.js (@libsql/client)
If you want to stick with an official libSQL client without C++ compilation errors, the JavaScript/TypeScript SDK (@libsql/client) is pure JS/WASM-backed and installs without any build toolchains on Windows.

Since you already have TypeScript files like backfill_from_kalshi.ts in your workspace, Hermes can write a lightweight Node/Bun runner:

Install @libsql/client via npm or pnpm:

Bash
npm install @libsql/client dotenv
Execute the backfill with npx tsx scripts/turso_backfill.ts.

Quick Recommendation
If you want Hermes to keep the script in Python, tell Hermes to "Use httpx to POST directly to Turso's /v2/pipeline HTTP endpoint." This will resolve the Windows compilation block immediately.