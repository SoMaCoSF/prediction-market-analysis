#!/usr/bin/env python3
"""
WTI hourly settlement watcher.
Monitors WTI spot price vs Kalshi positions, alerts on settlement.
Run: python scripts/wti_settlement_watch.py
"""
import os, sys, json, time, base64
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

import httpx

ROOT = Path(__file__).resolve().parent.parent
KALSHI_HOST = 'https://api.elections.kalshi.com/trade-api/v2'
STATE_FILE = ROOT / 'data' / 'wti_watch_state.json'

def kalshi_sign(method, path, ts_ms, key_path):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    full = '/trade-api/v2' + path.split('?')[0]
    msg = f'{ts_ms}{method.upper()}{full}'.encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return base64.b64encode(sig).decode()

def get_kid_kpath():
    kid = os.getenv('KALSHI_KEY_ID')
    kpath = str(ROOT / '.kalshi_key.pem')
    return kid, kpath

def kalshi_get(path, params=None):
    kid, kpath = get_kid_kpath()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign('GET', path, ts, kpath)
    h = {'KALSHI-ACCESS-KEY': kid, 'KALSHI-ACCESS-SIGNATURE': sig, 'KALSHI-ACCESS-TIMESTAMP': ts}
    r = httpx.get(f'{KALSHI_HOST}{path}', headers=h, params=params, timeout=20)
    return r

def get_wti_price():
    r = httpx.get('https://query1.finance.yahoo.com/v8/finance/chart/CL=F',
                  params={'interval':'1m','range':'1d'}, timeout=15,
                  headers={'User-Agent':'Mozilla/5.0'})
    if r.status_code == 200:
        return r.json()['chart']['result'][0]['meta']['regularMarketPrice']
    return None

def get_wti_positions():
    """Get our WTI positions for the current hourly."""
    r = kalshi_get('/portfolio/positions')
    if r.status_code != 200:
        return []
    mp = r.json().get('market_positions', [])
    return [p for p in mp if 'KXWTIH' in p.get('ticker', '') and float(p.get('position_fp', 0)) > 0]

def check_settlement(ticker):
    """Check if a market has settled and what the result was."""
    r = kalshi_get(f'/markets/{ticker}')
    if r.status_code == 200:
        m = r.json().get('market', r.json())
        return m.get('result'), m.get('status')
    return None, None

def main():
    print(f'[{datetime.now(UTC).strftime("%H:%M:%S")} UTC] WTI Settlement Watcher started')
    
    while True:
        try:
            price = get_wti_price()
            positions = get_wti_positions()
            now = datetime.now(UTC)
            
            print(f'\n[{now.strftime("%H:%M:%S")} UTC] WTI: ${price:.2f}' if price else f'[{now.strftime("%H:%M:%S")} UTC] WTI: PRICE UNAVAILABLE')
            
            if not positions:
                print('  No active WTI positions')
                # Check if we should look for new opportunities
                # (would be handled by the scanner, not this watcher)
            else:
                total_cost = 0
                total_value = 0
                for p in positions:
                    t = p.get('ticker', '')
                    strike = float(t.split('-T')[1]) if '-T' in t else 0
                    pos = float(p.get('position_fp', 0))
                    cost = float(p.get('total_traded_dollars', 0))
                    pnl = float(p.get('realized_pnl_dollars', 0))
                    result, status = check_settlement(t)
                    
                    if price:
                        dist = price - strike
                        in_money = 'YES WIN' if dist > 0 else 'NO LOSS'
                        print(f'  {t}: {pos} shares | strike ${strike:.2f} | oil ${dist:+.2f} | {status} | result={result}')
                        if result:
                            if result == 'yes':
                                print(f'    -> SETTLED YES! +${pos - cost:.2f} profit')
                            else:
                                print(f'    -> SETTLED NO. -${cost:.2f} loss')
                        total_cost += cost
                        if dist > 0:
                            total_value += pos  # would settle at $1 each
                
                if price and positions:
                    print(f'  Total at risk: ${total_cost:.2f} | If all win: ${total_value:.2f} | Profit: ${total_value - total_cost:.2f}')
            
            # Save state
            state = {
                'timestamp': now.isoformat(),
                'wti_price': price,
                'positions': [{'ticker': p.get('ticker',''), 'position': p.get('position_fp','0'),
                              'cost': p.get('total_traded_dollars','0'), 'pnl': p.get('realized_pnl_dollars','0')}
                             for p in positions]
            }
            STATE_FILE.write_text(json.dumps(state, indent=2))
            
        except Exception as e:
            print(f'Error: {e}')
        
        time.sleep(60)  # check every minute

if __name__ == '__main__':
    main()
