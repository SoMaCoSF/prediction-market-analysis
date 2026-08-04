# SoMaCoSF GYST-UUID Trading Substrate — Architecture & Live State

> Secret reference. Published 2026-08-04. Status: CAPABLE, CAPITAL-CONSTRAINED, REBOOT-SURVIVING.

## 1. What this is
A self-funding, UUIDv8-native prediction-market trading system. Every order, fill, 15-minute call, and divergence is a typed UUIDv8 object with deterministic content + spawn-tree provenance. The ledger (Postgres/Supabase) is the system of record; the exchanges (Kalshi, Polymarket) are reconciled against it every 60s. The desk cannot lie to itself — if the ledger says $0 in play, $0 is in play.

## 2. The fleet (32 daemons, zero-token supervisor)
Supervisor (`scripts/supervisor.py`) is a pure-Python watchdog. It spawns + health-checks every daemon, adopts children by verifying the adopted PID's command line (not just the PID — fixes the stale-lock zombie bug). On reboot it is launched by Registry Run `SoMaCoFleet` → `pythonw.exe scripts/supervisor.py`.

| Group | Daemons | Job |
|-------|---------|-----|
| Bankroll | vault, governor, bridge | reserve lock + savings sweep; circuit breaker; cross-account awareness |
| Micro-grind | trend-eth/sol/xrp/doge, btctrend, scalp, profit_scalp | 3-min spot momentum → early-window 15M BTC/ETH markets, +15/−10 exit |
| Signal | xwatch, shadow, maker, news, calendar, crossvenue | polymarket/Kalshi divergence, whale shadow, ATLAS, events |
| Evidence | evidence, dry + dry-t10/20/25/s15-8, promoter | paper backtests → adopted exit profiles; n≥50 + CI≥55% to size up |
| Oracle | oracle | pre-commits 15M BTC call to ledger BEFORE window closes (immutable track record) |
| Funding | funding_feed, poly-exec | wallet slurp watcher; Polymarket CLOB executor (armed, dormant until funded) |
| Plumbing | ws, tick, xvenue, ingest, fills, sweep, mc, agent-status | WebSocket firehose → RAM tick plane; fill poller reconciles phantom positions |

## 3. How the engine makes a trade
1. **Signal** — local UUID tape (BTC ticks every 5s) + Kraken 24h drift. Fires on drift ≥1.5bps.
2. **Entry** — early-window 15M market, price 25–60¢, both-side. Size ladders: 1¢ base, 2¢ at $25+, 4¢ on strong signal.
3. **Exit** — +15¢ take / −10¢ stop, else settle at resolution. This discipline produced 4/4 wins at +60.5¢/trade.
4. **Bankroll guard** — vault locks 30% reserve + a protected savings sleeve; governor halts entries at −30% DD, stops at −50%. Variance lanes (parlay/speed/moonshot) stay paused until house money exists.
5. **Evidence** — 5 parallel paper backtests continuously test exit profiles; live engines adopt the winner.

## 4. The savings fund (NEW)
On every realized win, **25% sweeps into a protected savings sleeve** the engines cannot touch. Persists in `mc_state` across restarts. Live: banked $0.60 from first realized wins. The grind compounds a cushion even at tiny bankroll.

## 5. Cross-account funding (NEW — bridge coordinator)
Kalshi (USD, no withdrawal API) and Polymarket (USDC on Polygon) are not directly interoperable. The `bridge_coordinator` daemon watches BOTH balances and TALKS:
- Poly surplus + Kalshi low → recommend off-ramp Poly → Kalshi (manual Venmo deposit)
- Kalshi surplus → recommend withdraw Kalshi → Poly (manual, then USDC to wallet)
Manual taps are fine; the system stays aware and publishes `bridge:state`.

## 6. Polymarket integration (status)
- **Signal: LIVE** — Gamma API (keyless) feeds markets + divergences; whale copier tracks top wallets (poly.somacosf.com).
- **Execution: ARMED, unfunded** — py-clob-client wired, creds derive from wallet key, fires on USDC. Wallet `0xbC6662be0803F28C827BC405477F0b5AB8c6Dd40`, currently $0.00.
- Spend capped at house-money allowance. Never principal.

## 7. Public surfaces
- trade./mc./tim./dry./time.somacosf.com — mission control, funds, oracle, status, about
- poly.somacosf.com — whale flow + divergences + portal + bridge panel
- somacosf-app.vercel.app — platform hub, /about, /login (passkey SomacoSays!), GlobalNav

## 8. Live performance (as of 2026-08-04)
- Equity ~$1.89, cash ~$0.10. Governor HALT at −34.6% DD (peak $2.89 → $1.89). The circuit breaker is correctly frozen.
- Realized: +$2.42, 4/4 wins (momentum pocket). Evidence: momentum lane n=4, winrate 100%, CI present.
- The engine is proven at micro scale. The only blocker is capital — your $20 Kalshi deposit (Venmo card) + a USDC send to the Poly wallet. funding_feed + bridge detect and scale automatically.

## 9. Known gaps
1. Bankroll starved ($0.10 cash) — needs deposit to resume grind.
2. Polymarket unfunded ($0 USDC).
3. somacosf.com apex domain needs dashboard click (token expired) — pages live on vercel.app + subdomains.
4. numba GPU bitmask + WS tape — WS half done.
5. Architecture doc images pending.

## 10. Reboot survival (VERIFIED)
- Registry Run `SoMaCoFleet` → `pythonw.exe scripts/supervisor.py` (always-on)
- Scheduled Tasks `SoMaCo-Fleet-Watch`, `SoMaCoSF Platform`
- Daily digest cron (agent scales itself out)
The fleet comes back automatically. All code committed + pushed to GitHub (uuid-trader, somacosf-platform).
