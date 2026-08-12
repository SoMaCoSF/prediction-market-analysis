import os, sys, json, time, base64, uuid, random
sys.path.insert(0, 'scripts')
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path

KEY_ID = os.getenv('KALSHI_KEY_ID')
KEY_PATH = Path('.kalshi_key.pem')

# NEW Kalshi API endpoint
BASE = 'https://api.elections.kalshi.com'

def sign_request(method, path, body=''):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    ts = str(int(time.time() * 1000))
    msg = f'{ts}{method.upper()}/trade-api/v2{path.split("?")[0]}' + body
    sig = key.sign(msg.encode(), padding.PSS(padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return {'KALSHI-ACCESS-KEY': KEY_ID, 'KALSHI-ACCESS-TIMESTAMP': ts, 'KALSHI-ACCESS-SIGNATURE': base64.b64encode(sig).decode()}

import httpx

# Test new API
headers = sign_request('GET', '/portfolio/balance')
r = httpx.get(BASE + '/portfolio/balance', headers=headers)
print('BALANCE', r.status_code, r.text[:300])

headers = sign_request('GET', '/portfolio/positions')
r = httpx.get(BASE + '/portfolio/positions', headers=headers)
print('POSITIONS', r.status_code, r.text[:500])
