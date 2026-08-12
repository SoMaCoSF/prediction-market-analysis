#!/usr/bin/env python3
"""
Micro-grind cycler: monitors settled positions, recycles freed capital
into new cheap MVE parlay bets. Runs continuously.

Strategy:
- Poll portfolio every 60s
- When positions settle and cash increases, sweep freed cash into new bets
- Target: asks 1-10c, 5-10 shares each, max $3 per cycle
- Skip markets already held
- Prioritize soonest-closing for fastest capital recycle

Run: python scripts/micro_grind_cycler.py
"""
import os, sys, json, time, base64, uuid
from datetime import datetime, UTC
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / '.env')

import httpx

ROOT = Path(__file__).resolve().parent.parent
KALSHI_HOST = 'https://external-api.kalshi.com/trade-api/v2'
STATE_FILE = ROOT / 'data' / 'wti_watch_state.json'
LOG_FILE = ROOT / 'data' / 'micro_grind_log.jsonl'

# Grind params
MAX_BET_PRICE = 0.10      # max 10c per share
MIN_ASK_SIZE = 50          # min 50 shares available
SHARES_PER_BET = 5         # 5 shares per market
MAX_CYCLE_SPEND = 5.00     # max $3 per cycle
MIN_CASH_TO_TRADE = 0.25  # need at least $1 free cash to bother
RESERVE_CASH = 0.50        # keep $2 reserve, don't deploy below this


def kalshi_sign(method, path, ts_ms, key_path):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(Path(key_path).read_bytes(), password=None)
    full = '/trade-api/v2' + path.split('?')[0]
    msg = f'{ts_ms}{method.upper()}{full}'.encode()
    sig = key.sign(msg, padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH), hashes.SHA256())
    return base64.b64encode(sig).decode()


def get_keys():
    kid = os.getenv('KALSHI_KEY_ID')
    kpath = str(ROOT / '.kalshi_key.pem')
    return kid, kpath


def kalshi_get(path, params=None):
    kid, kpath = get_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign('GET', path, ts, kpath)
    h = {'KALSHI-ACCESS-KEY': kid, 'KALSHI-ACCESS-SIGNATURE': sig, 'KALSHI-ACCESS-TIMESTAMP': ts}
    r = httpx.get(f'{KALSHI_HOST}{path}', headers=h, params=params, timeout=20)
    return r


def kalshi_post(path, body):
    kid, kpath = get_keys()
    ts = str(int(time.time() * 1000))
    sig = kalshi_sign('POST', path, ts, kpath)
    h = {'KALSHI-ACCESS-KEY': kid, 'KALSHI-ACCESS-SIGNATURE': sig, 'KALSHI-ACCESS-TIMESTAMP': ts, 'Content-Type': 'application/json'}
    r = httpx.post(f'{KALSHI_HOST}{path}', json=body, headers=h, timeout=20)
    return r


def get_portfolio():
    r = kalshi_get('/portfolio/balance')
    if r.status_code != 200:
        return None
    b = r.json()
    cash = float(b.get('balance_dollars', 0))
    portfolio_value = b.get('portfolio_value', 0) / 100

    r = kalshi_get('/portfolio/positions')
    if r.status_code != 200:
        return None
    mp = r.json().get('market_positions', [])
    active = [p for p in mp if float(p.get('position_fp', 0)) > 0]
    held_tickers = set(p.get('ticker', '') for p in active)

    return {
        'cash': cash,
        'portfolio_value': portfolio_value,
        'active': active,
        'settled': [],
        'held_tickers': held_tickers,
        'total_shares': sum(float(p.get('position_fp', 0)) for p in active),
        'total_invested': sum(float(p.get('total_traded_dollars', 0)) for p in active),
        'realized_pnl': 0.0,
    }


def scan_opportunities(held_tickers):
    """Scan for cheap MVE markets not already held."""
    candidates = []
    cursor = ''
    pages = 0
    while pages < 15:
        params = {'limit': 200, 'status': 'open'}
        if cursor:
            params['cursor'] = cursor
        r = kalshi_get('/markets', params=params)
        if r.status_code != 200:
            break
        data = r.json()
        markets = data.get('markets', [])
        if not markets:
            break
        for m in markets:
            t = m.get('ticker', '')
            if t in held_tickers:
                continue
            yad = float(m.get('yes_ask_dollars', '0') or '0')
            yas = float(m.get('yes_ask_size_fp', '0') or '0')
            close = m.get('close_time', '')
            if 0 < yad <= MAX_BET_PRICE and yas >= MIN_ASK_SIZE:
                candidates.append({'ticker': t, 'ask': yad, 'ask_size': yas, 'close': close})
        cursor = data.get('cursor', '')
        pages += 1
        if not cursor:
            break

    # Deduplicate by event
    seen = set()
    unique = []
    for c in candidates:
        et = c['ticker'].rsplit('-', 1)[0] if '-' in c['ticker'] else c['ticker']
        if et not in seen:
            seen.add(et)
            unique.append(c)

    unique.sort(key=lambda c: (c['close'] or '9999', c['ask']))
    return unique


def fire_bets(candidates, budget):
    """Place IoC orders on candidates, return fills."""
    spent = 0
    fills = []
    for c in candidates[:60]:
        if spent >= budget:
            break
        ask = c['ask']
        order_body = {
            'ticker': c['ticker'],
            'client_order_id': f'grind-{uuid.uuid4().hex[:12]}',
            'side': 'bid',
            'count': f'{SHARES_PER_BET}.00',
            'price': f'{ask:.4f}',
            'time_in_force': 'immediate_or_cancel',
            'self_trade_prevention_type': 'taker_at_cross',
            'post_only': False,
            'cancel_order_on_pause': False,
            'reduce_only': False,
            'subaccount': 0,
            'exchange_index': -1,
        }
        r = kalshi_post('/portfolio/events/orders', order_body)
        if r.status_code in (200, 201):
            resp = r.json()
            fc = float(resp.get('fill_count', '0'))
            if fc > 0:
                avg_price = float(resp.get('average_fill_price', str(ask)))
                fee = float(resp.get('average_fee_paid', '0'))
                cost = avg_price * fc + fee
                spent += cost
                fills.append({
                    'ticker': c['ticker'],
                    'shares': fc,
                    'price': avg_price,
                    'cost': cost,
                    'close': c['close'],
                })
    return fills, spent


def update_state(portfolio):
    """Write state file for the web dashboard."""
    try:
        wti_price = None
        r = httpx.get('https://query1.finance.yahoo.com/v8/finance/chart/CL=F',
                      params={'interval': '1m', 'range': '1d'}, timeout=10,
                      headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code == 200:
            wti_price = r.json()['chart']['result'][0]['meta']['regularMarketPrice']
    except:
        pass

    state = {
        'timestamp': datetime.now(UTC).isoformat(),
        'wti_price': wti_price,
        'cash': portfolio['cash'],
        'portfolio_value': portfolio['portfolio_value'],
        'active_count': len(portfolio['active']),
        'settled_count': len(portfolio['settled']),
        'realized_pnl': portfolio['realized_pnl'],
        'total_shares': portfolio['total_shares'],
        'total_invested': portfolio['total_invested'],
        'max_return': portfolio['total_shares'],
        'positions': [
            {
                'ticker': p.get('ticker', ''),
                'position': p.get('position_fp', '0'),
                'cost': p.get('total_traded_dollars', '0'),
                'pnl': p.get('realized_pnl_dollars', '0'),
            }
            for p in portfolio['active']
        ],
    }
    STATE_FILE.write_text(json.dumps(state, indent=2))


def log_event(event):
    """Append to grind log."""
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps({**event, 'ts': datetime.now(UTC).isoformat()}) + '\n')


def main():
    print(f'[{datetime.now(UTC).strftime("%H:%M:%S")} UTC] Micro-grind cycler started')
    print(f'  Max bet: {MAX_BET_PRICE} | Shares/bet: {SHARES_PER_BET} | Max cycle: ${MAX_CYCLE_SPEND} | Reserve: ${RESERVE_CASH}')

    last_cash = None
    cycle_count = 0

    while True:
        try:
            portfolio = get_portfolio()
            if not portfolio:
                print(f'  Portfolio fetch failed, retrying...')
                time.sleep(60)
                continue

            now = datetime.now(UTC)
            cash = portfolio['cash']

            # Detect capital freed (cash increased since last check)
            freed = 0
            if last_cash is not None and cash > last_cash + 0.01:
                freed = cash - last_cash
                print(f'\n[{now.strftime("%H:%M:%S")} UTC] CASH FREED: +${freed:.2f} (${last_cash:.2f} → ${cash:.2f})')

            # Check if we should deploy
            deployable = cash - RESERVE_CASH
            if deployable >= MIN_CASH_TO_TRADE:
                cycle_count += 1
                cycle_budget = min(deployable, MAX_CYCLE_SPEND)
                print(f'\n[{now.strftime("%H:%M:%S")} UTC] CYCLE #{cycle_count}: deploying ${cycle_budget:.2f}')
                print(f'  Cash: ${cash:.2f} | Active: {len(portfolio["active"])} | Shares: {portfolio["total_shares"]:.0f} | Max return: ${portfolio["total_shares"]:.2f}')

                candidates = scan_opportunities(portfolio['held_tickers'])
                print(f'  Candidates: {len(candidates)}')

                if candidates:
                    fills, spent = fire_bets(candidates, cycle_budget)
                    if fills:
                        new_shares = sum(f['shares'] for f in fills)
                        print(f'  FILLED: {len(fills)} bets, {new_shares:.0f} shares, ${spent:.4f} spent')
                        log_event({
                            'type': 'cycle',
                            'cycle': cycle_count,
                            'fills': len(fills),
                            'shares': new_shares,
                            'spent': spent,
                            'cash_before': cash,
                        })
                    else:
                        print(f'  No fills this cycle')
                else:
                    print(f'  No candidates available')
            else:
                if last_cash is not None and abs(cash - last_cash) > 0.01:
                    print(f'  Cash: ${cash:.2f} (below deploy threshold, reserve ${RESERVE_CASH})')

            # Update state file for dashboard
            update_state(portfolio)

            last_cash = cash

            # Status line
            print(f'  [{now.strftime("%H:%M:%S")} UTC] cash=${cash:.2f} active={len(portfolio["active"])} shares={portfolio["total_shares"]:.0f} invested=${portfolio["total_invested"]:.2f} max=${portfolio["total_shares"]:.2f} pnl=${portfolio["realized_pnl"]:.2f}')

        except Exception as e:
            print(f'  Error: {e}')

        time.sleep(60)


if __name__ == '__main__':
    main()
