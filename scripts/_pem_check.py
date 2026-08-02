# verify .kalshi_key.pem parses as an RSA private key (prints only key metadata)
from pathlib import Path
from cryptography.hazmat.primitives import serialization

p = Path(__file__).resolve().parent.parent / ".kalshi_key.pem"
if not p.exists():
    print("PEM MISSING")
    raise SystemExit(1)
raw = p.read_bytes()
try:
    key = serialization.load_pem_private_key(raw, password=None)
    print("PEM OK | type:", type(key).__name__, "| size:", key.key_size, "bits")
except Exception as e:
    print("PEM PARSE FAIL:", repr(e)[:200])
    raise SystemExit(1)
