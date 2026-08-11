#!/usr/bin/env python3
# file_id: SOM-PY-1007-v1.0.0 name: live_smoke_test.py description: Live Kalshi smoke test — checks balance, scans open markets, and submits one small order when edge is present project_id: PREDICTION-MARKET-ANALYSIS category: script tags: [kalshi, live, smoke-test, trading, execution] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
import os, sys, json, time, base64
from pathlib import Path
import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path('.').resolve()

def load_env():
    env = {}
    p = ROOT / '.env'
    if not p.exists():
        return env
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' in line:
            k, v = line.split('=', 1)
            env[k] = v
    return env

def signed_headers(method: str, path: str, env: dict) -> dict:
    kid = env.get('KALSHI_KEY_ID')
    kpath = env.get('KALSHI_PRIVATE_KEY_PATH') or str(ROOT / '.kalshi_key.pem')
    key_bytes = Path(kpath).read_bytes()
    ts = str(int(time.time() * 1000))
    full = '/trade-api/v2' + path.split('?')[0]
    msg = f'{ts}{method.upper()}{full}'.encode()
    key = serialization.load_pem_private_key(key_bytes, password=None)
    sig = base64.b64encode(key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())).decode()
    return {'KALSHI-ACCESS-KEY': kid, 'KALSHI-ACCESS-SIGNATURE': sig, 'KALSHI-ACCESS-TIMESTAMP': ts}

def kget(env, path, params=None):
    host = env.get('KALSHI_HOST', 'https://api.elections.kalshi.com/trade-api/v2')
    headers = signed_headers('GET', path, env)
    with httpx.Client(timeout=20) as cx:
        r = cx.get(host + path, headers=headers, params=params)
    return r.status_code, r.text

def kpost(env, path, body):
    host = env.get('KALSHI_HOST', 'https://api.elections.kalshi.com/trade-api/v2')
    headers = signed_headers('POST', path, env)
    headers['Content-Type'] = 'application/json'
    with httpx.Client(timeout=20) as cx:
        r = cx.post(host + path, headers=headers, json=body)
    return r.status_code, r.text

def main():
    env = load_env()
    kid = env.get('KALSHI_KEY_ID')
    kpath = env.get('KALSHI_PRIVATE_KEY_PATH') or str(ROOT / '.kalshi_key.pem')
    print('KALSHI_KEY_ID:', kid)
    print('KALSHI key path:', kpath)
    print('Key exists:', Path(kpath).exists())

    code, body = kget(env, '/portfolio/balance')
    print('balance status:', code)
    print('balance body:', body[:300])

    code2, body2 = kget(env, '/markets', params={'limit': 20, 'status': 'open', 'category': 'sports'})
    print('markets status:', code2)
    data = json.loads(body2)
    markets = data.get('markets', [])
    print('markets count:', len(markets))
    for m in markets[:5]:
        print(' ', m.get('ticker'), '|', (m.get('title') or '')[:50], '| yes_bid:', m.get('yes_bid_dollars'), 'yes_ask:', m.get('yes_ask_dollars'))

    pick = None
    for m in markets:
        ya = float(m.get('yes_ask_dollars') or 0)
        yb = float(m.get('yes_bid_dollars') or 0)
        vol = float(m.get('volume') or 0)
        if ya > 0 and ya <= 0.25 and vol > 0:
            pick = m
            break
    if not pick:
        print('no actionable market found')
        return
    print('pick:', pick.get('ticker'), 'ask:', pick.get('yes_ask_dollars'), 'vol:', pick.get('volume'))
    order = {
        'ticker': pick.get('ticker'),
        'side': 'yes',
        'action': 'buy',
        'count': '1',
        'price': str(pick.get('yes_ask_dollars')),
        'time_in_force': 'immediate_or_cancel',
        'reduce_only': False,
        'client_order_id': f"smoke-{int(time.time())}"
    }
    code3, body3 = kpost(env, '/portfolio/events/orders', order)
    print('order status:', code3)
    print('order body:', body3[:500])

if __name__ == '__main__':
    main()
