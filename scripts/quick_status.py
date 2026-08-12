import os, sys, json, time, base64, uuid, random
sys.path.insert(0, 'scripts')
from dotenv import load_dotenv
load_dotenv()
from pathlib import Path

KEY_ID = os.getenv('KALSHI_KEY_ID')
KEY_PATH = Path('.kalshi_key.pem')
BASE = 'https://api.elections.kalshi.com/trade-api/v2'
STATE = Path('data/wti_watch_state.json')

def sign_request(method, path, body=''):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)
    ts = str(int(time.time() * 1000))
    msg = ts + method + path + body
    sig = key.sign(msg.encode(), padding.PSS(padding.MGF1(hashes.SHA256()), salt_length=20), hashes.SHA256())
    return {'KALSHI-KEY-ID': KEY_ID, 'KALSHI-TIMESTAMP': ts, 'KALSHI-SIGNATURE': base64.b64encode(sig).decode()}

import httpx

# Get balance
headers = sign_request('GET', '/portfolio/balance')
r = httpx.get(BASE + '/portfolio/balance', headers=headers)
print('BALANCE', r.status_code, r.text[:200])

# Get positions to count existing
headers = sign_request('GET', '/portfolio/positions')
r = httpx.get(BASE + '/portfolio/positions', headers=headers)
print('POSITIONS', r.status_code)
if r.status_code == 200:
    positions = r.json().get('positions', [])
    print(f'Existing positions: {len(positions)}')
else:
    print(r.text[:200])
    positions = []
