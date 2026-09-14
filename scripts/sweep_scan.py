#!/usr/bin/env python3
"""sweep_scan.py — READ-ONLY dormant-money scanner for the Kalshi account.

Answers: "is there money sitting in positions that could be swept into cash?"
GET endpoints only. Never places, cancels, or modifies orders.

  - /portfolio/positions  -> every market position row (nonzero = real holding)
  - /portfolio/orders     -> resting orders (context; stale ones flagged)
  - /portfolio/balance    -> cash truth
  - public /markets/{t}   -> current exit quotes per holding

Exit value per holding: long-YES exits at yes_bid; long-NO exits at 100 - yes_ask.
Both are DISPLAY quotes — depth is verified separately before any real sweep.

Writes data/sweep_scan/latest.json. Prints a ranked table + totals.
"""
import os
import sys
import json
import time
import base64
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'data' / 'sweep_scan'
OUT.mkdir(parents=True, exist_ok=True)

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / '.env')
except Exception:
    envf = ROOT / '.env'
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

KALSHI_HOST = 'https://api.elections.kalshi.com/trade-api/v2'
PUB = 'https://api.elections.kalshi.com/trade-api/v2'

import requests


def get_keys():
    kid = os.getenv('KALSHI_KEY_ID')
    kpath = str(ROOT / '.kalshi_key.pem')
    if not kid or not Path(kpath).exists():
        raise SystemExit('FATAL: missing KALSHI_KEY_ID or .kalshi_key.pem')
    return kid, kpath


def kalshi_sign(method, path, ts_ms, key_path):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    full = '/trade-api/v2' + path.split('?')[0]
    msg = f'{ts_ms}{method.upper()}{full}'.encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                                    salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return base64.b64encode(sig).decode()


def kalshi_get(path, params=None):
    kid, kpath = get_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign('GET', path, ts, kpath)
    headers = {
        'KALSHI-ACCESS-KEY': kid,
        'KALSHI-ACCESS-TIMESTAMP': ts,
        'KALSHI-ACCESS-SIGNATURE': sig,
    }
    r = requests.get(KALSHI_HOST + path, headers=headers, params=params, timeout=30)
    if r.status_code != 200:
        print(f'HTTP {r.status_code} on {path}: {r.text[:300]}')
        r.raise_for_status()
    return r.json()


def public_market(ticker):
    try:
        r = requests.get(f'{PUB}/markets/{ticker}', timeout=20)
        if r.status_code == 200:
            return r.json().get('market', {})
    except Exception:
        pass
    return {}


print('== sweep_scan (GET only) ==')
print('now_utc:', datetime.now(timezone.utc).isoformat())

bal = kalshi_get('/portfolio/balance')
cash = int(bal.get('balance') or 0)
pv = int(bal.get('portfolio_value') or 0)
print(f'cash: {cash}c (${cash / 100:.2f}) | portfolio_value: {pv}c')

pos = kalshi_get('/portfolio/positions', params={'limit': 200})
rows = pos.get('market_positions') or pos.get('event_positions') or []
zero_rows = 0
holdings = []
for row in rows:
    fp = float(row.get('position_fp') or 0.0)
    t = row.get('ticker')
    if fp == 0.0:
        zero_rows += 1
        continue
    m = public_market(t)
    yes_bid = float(m.get('yes_bid_dollars') or 0) * 100
    yes_ask = float(m.get('yes_ask_dollars') or 0) * 100
    count = abs(fp)
    side = 'yes' if fp > 0 else 'no'
    exit_c = (yes_bid if side == 'yes' else (100 - yes_ask)) if yes_ask or yes_bid else 0.0
    value = round(count * exit_c / 100.0, 2)
    holdings.append({
        'ticker': t, 'side': side, 'count': count,
        'exit_cents': round(exit_c, 1), 'value_usd': value,
        'result': m.get('result'), 'close': m.get('close_time'),
        'status': m.get('status'),
    })

holdings.sort(key=lambda h: -h['value_usd'])
total_value = round(sum(h['value_usd'] for h in holdings), 2)

orders = kalshi_get('/portfolio/orders', params={'limit': 100, 'status': 'resting'})
resting = orders.get('orders') or []

print(f'\n== HOLDINGS (nonzero) — {len(holdings)} of {len(rows)} rows ({zero_rows} zero rows) ==')
print(f"{'ticker':42s} {'side':4s} {'count':>7s} {'exit¢':>6s} {'value$':>7s}  result  close")
for h in holdings:
    print(f"{h['ticker']:42s} {h['side']:4s} {h['count']:7.2f} {h['exit_cents']:6.1f} {h['value_usd']:7.2f}  {str(h['result']):4s}  {str(h['close'])[:10]}")
print(f'\nTOTAL sweepable value: ${total_value:.2f}')

print(f'\n== RESTING ORDERS ({len(resting)}) ==')
for o in resting:
    print(f"  {o.get('ticker')} {o.get('side')} {o.get('action')} count={o.get('remaining_count') or o.get('count')} price={o.get('yes_price') or o.get('no_price')} since={str(o.get('created_time'))[:19]}")

payload = {
    'at': datetime.now(timezone.utc).isoformat(),
    'cash_cents': cash, 'portfolio_value_cents': pv,
    'holdings': holdings, 'total_value_usd': total_value,
    'resting_orders': resting, 'zero_rows': zero_rows,
}
(OUT / 'latest.json').write_text(json.dumps(payload, indent=2))
print('\nsaved:', OUT / 'latest.json')

candidates = [h for h in holdings if h['value_usd'] >= 0.50 and (h['status'] == 'active' or not h['result'])]
print(f'\nSWEEP CANDIDATES (>= $0.50 executable, market live): {len(candidates)}')
for h in candidates:
    print(f"  {h['ticker']} {h['side']} x{h['count']:.0f} @ {h['exit_cents']}c = ${h['value_usd']:.2f}")
if not candidates:
    print('  none — nothing worth sweeping right now')