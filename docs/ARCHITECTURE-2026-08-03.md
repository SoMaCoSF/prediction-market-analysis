# SoMaCo UUIDv8 Trading System — Full Architecture (2026-08-03)

> **North star:** every object is a **GYST UUIDv8** — routable, bettable, transactional. Markets, orders, fills, forecasts, articles, votes, ticks. Each is a 128-bit self-describing identity; children spawn from parents, so the provenance chain (story → forecast → bet → fill → settle) is native to the bit layout.

## Bit layout v3.0.0
- **high:** type(12) | namespace(12) | timestamp(24) | version(4) | fractal(12)
- **low:** variant(2) | provenance(4) | signal(16) | content(42)
- Updates spawn CHILD UUIDs (`ns = fnv1a12(parent)`); roll-ups = bitmask routing on ns+fractal; low-42 is deterministic sha256 — never random.

## Type codes in production
| Code | Object |
|---|---|
| 0x3B0 | Kalshi market |
| 0x3A4/0x3A5 | order bid / ask |
| 0x3A6 | exchange ack |
| 0x3A7 | fill |
| 0x3A9 | settle |
| 0x3AA | mark |
| 0x326 | FORECAST (news/supply-chain) |
| 0x3D2 | SHADOW (whale print) |
| 0x3D3 | XSIGNAL (X sentiment) |
| 0x3D4 | ARTICLE (TIME stories — bets parent on them) |
| 0x3D5 | DIVERGENCE (cross-venue) |

## The fleet (22 lanes, zero model tokens)
**Execution:** mission_control (kill switch, caps, ledger) on :8420.
**Trading lanes:** btctrend (near-continuous BTC 15M), trend-eth/sol/xrp/doge (parameterized trend_engine, 2-concurrent, 2ct on strong signals), scalp (5-series both-side exits), maker (zero-fee spread), parlay (10% cash into 2-10¢ combo tails), speed-btc/eth ($3 churn lanes), calendar (cross-market micro momentum, closing<6h), xvenue (Polymarket↔Kalshi divergence), copier (whale-wallet copies), news (supply-chain forecasts + bets).
**Wire-speed spine:** kalshi_ws (official WS v2) → tick_service :8421 (RAM rings, sub-ms reads) → engines; batch flush to Postgres (GIS/pgvector).
**Signal lanes:** shadow (Polymarket whale flow), xwatch (X sentiment), evidence (Wilson-CI verdicts: PROVEN/FORMING/DEAD with pre-registered gates).
**Ops:** supervisor (adopt-or-spawn, hung-restart, crash-capped), fills (fill sync + account publish, decoupled), sweep ($100 increments at $200 → Venmo alert), dry ×4 (parameter-sweep paper lanes).

## Honesty machinery
- **Exchange truth only:** FILLED means fill_count_fp>0; P&L from /portfolio/positions + settles.
- **Evidence engine:** per-lane win-rate with Wilson 95% CI + expectancy/trade. PROVEN needs n≥50 AND lower-CI≥0.55 AND exp>0. DEAD gets declared publicly.
- **Losses published:** the panel shows the drawdowns ($24.98 → $134 → $57 → $102 arc is all visible).

## Surfaces
- **trade.somacosf.com** — live control: equity hero + sparkline, lanes strip, evidence verdicts, sweep banner, bet tile, positions.
- **time.somacosf.com** — the AI times: UUID-minted stories, votes, discussion, OUR CALLS forecasts, tradable stories (slider + PIN, bets parent on the story UUID). /about = the manifesto.
- **tim.somacosf.com** — guest phone betting (PIN, $2/order, $20/day).
- **dry.somacosf.com** — paper proof terminal.

## Survivability
Windows scheduled tasks restart the supervisor at logon + every 5 min (atomic locks make dupes harmless). Ledger SoT = Supabase. Code = private GitHub repo. Rebuild-from-total-loss: ~10 min (docs/SURVIVABILITY.md).

## Numbers (exchange-verified, 2026-08-03)
- Bankroll arc: $24.98 → $134 peak → $57 drawdown → $102+ (live)
- Ledger: 10,600+ orders · 7,170+ fills · realized +$2.42 momentum lane
- Paper edge: 47/3 (94%) across 60-min dry runs; live gate: 50 trades @ ≥58% lower-CI before size-up
- Tick plane: 2,000+ ticks/min buffered across 5 symbols
