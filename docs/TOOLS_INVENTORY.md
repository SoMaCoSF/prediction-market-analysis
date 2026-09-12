# TOOLS INVENTORY — prediction-market-analysis

> Static scan **2026-09-12** (Hermes operator session from the `SoMaCoSF/gev-supplychain` side). Method: every source file's `file_id` header / docstring / first comment extracted by script; **nothing was executed**. Repo HEAD at scan: `20f0699`.
> Totals: **292 source files** — scripts/ 165 (+5 strategies), app/ 48, src/ 56 (research package), swarm_watcher/ 8, tests/ 5, stream-view/ 1, root 4. Static HTML surfaces (app/public, mc_static, infographic, docs dumps) not scanned. Descriptions quoted as-written in files.

## Legend

| Cat | Section |
|---|---|
| A | **Core & control — the always-on spine** — Singleton locks, kill switch, floor guard, ledger writer, governor/oracle/vault. Source of truth: FLEET_ARCHITECTURE.md. |
| B | **Trading engines & lanes** — Anything that fires live Kalshi orders (or is designed to). Many are experimental sleeves — check the fleet-ops skill before running. |
| C | **Signals & discovery** — Feeds that watch the world and produce signals/discovery (news, whales, X, orderbooks). news_supply_engine.py is the supply-chain node mapper — reuse #1 for the GEV project. |
| D | **Paper & simulation** — Zero-real-money engines and proposers. |
| E | **Execution & exits** — Order placement, routing, position exits. kalshi_executor.py is the GO-gated V2 path. |
| F | **Ops, monitoring & reporting** — Watchers, self-checks, dashboards, tallies, recovery, evidence. |
| G | **Data, ledger & UUID infrastructure** — Backfills, Supabase/Turso sync, GYST UUID tools, runlog, schemas, market-data ingestion. |
| H | **Utility one-offs (`_*` debug/probe scripts)** — Historical one-shot scripts — schema applies, probes, debug dumps. Kept for archaeology; not fleet components. |
| I | **Shell / PowerShell launchers** — Install, provision, and relaunch tooling. |

Mod = file mtime (freshness signal). `—` = no extractable header.

## A — Core & control — the always-on spine  (10)

| Tool | Modified | Purpose |
|---|---|---|
| `bridge_coordinator.py` | 2026-08-04 | Cross-account bridge coordinator — watches Kalshi cash + Polymarket USDC, knows the flow rules between the two venues, and TALKS: publishes bridge:state and raise… |
| `fill_poller.py` | 2026-08-10 | Fill poller — syncs exchange fills into the UUID ledger (0x3A7 fills + position updates + realized P&L on sells) every 60s; zero tokens |
| `fleetlib.py` | 2026-08-11 | Fleet sanity — singleton locks (refuse double-run) + checkin heartbeats (stale = hung = supervisor restarts); the checkin sanity loop |
| `governor.py` | 2026-08-03 | Equity governor — the circuit breaker: tracks peak equity, HALTS engine entries at -30% drawdown, full-stop at -50%; publishes governor:state; engines check befor… |
| `mission_control.py` | 2026-08-10 | Mission control web server — terminal-UX dashboard for the UUID trader: corpus stats, Kalshi markets, ledger views, passkey-gated PAPER/FIRE controls, kill switch |
| `oracle.py` | 2026-08-03 | THE ORACLE — pre-commits the fleet's 15M BTC call to the ledger BEFORE the window closes (0x3D7 ORACLE_CALL mints), scores the last call on settle, publishes orac… |
| `supervisor.py` | 2026-08-11 | Zero-token watchdog — spawns all trading daemons, relaunches any that die (backoff-capped), heartbeats to runlog; the persistence layer |
| `tick_service.py` | 2026-08-03 | In-memory tick service — RAM ring buffers per symbol, sub-ms HTTP reads for engines, batched COPY flush to local Postgres (GIS/vector install); the wire-speed spi… |
| `uuid_ledger.py` | 2026-08-02 | UUID-native trading ledger — mint every order/fill/settlement as a GYST UUIDv8 child; reconcile exchange acks by low-42 bitmask (no lookup table); spawn-tree P&L |
| `vault.py` | 2026-08-04 | Bankroll vault daemon — every 60s reads Kalshi balance (RSA-PSS signed GET /portfolio/balance), locks a reserve = min($100, 50% of equity), computes trading allow… |

## B — Trading engines & lanes  (29)

| Tool | Modified | Purpose |
|---|---|---|
| `aggressive_hunter.py` | 2026-08-07 | Aggressive Kalshi hunter — only trades when real liquidity exists. |
| `btc15_bot.py` | 2026-08-02 | BTC 15-min momentum bot — spot-momentum signal vs Kalshi KXBTC15M lag, micro-size live fires through mission control, hard caps + session stop, UUID ledger tracking |
| `btc15m_watch.py` | 2026-08-15 | BTC-15m energy watcher + GO-gated micro-bet. |
| `btc_trend.py` | 2026-08-04 | BTC 15M trend thread — momentum from the local UUID tape (3-min spot momentum), trend-aligned early-window entries, both-side exits (+15/-10), supervised, zero to… |
| `chaos_monkey.py` | 2026-08-02 | Chaos monkey — random extreme-tail micro bets (1-5c) across all open Kalshi markets, hard $1 budget, shuffled, fill-verified |
| `crazy_round.py` | 2026-08-02 | Crazy round — immediate real-money momentum sleeve (5 crypto 15M, loose TTL) + tail basket, $4 hard cap, fill-verified |
| `crossvenue_engine.py` | 2026-08-11 | Cross-venue engine — Polymarket x Kalshi same-event divergence: when venues disagree >5c on a crypto market, mint 0x3D5 and bet the Kalshi side toward the deeper … |
| `crypto_short_optimizer.py` | 2026-08-07 | Crypto short optimizer — NO-side drift entries on 15M/1H/4H, +15c exits, direct Kalshi V2. |
| `external_explorer.py` | 2026-08-06 | external_explorer.py — external-market cash-up loop against live Kalshi data. |
| `fixed_hunter.py` | 2026-08-07 | Fixed Kalshi hunter — uses real market detail prices, IoC exits, continuous uptick. |
| `fleet_explorer.py` | 2026-08-06 | fleet_explorer.py — 8-hour aggressive cash-up loop. |
| `kalshi_hunter.py` | 2026-08-07 | Kalshi+++ universal hunter — trades ANY market with volume using mean-reversion. |
| `kalshi_uuid_bot.py` | 2026-08-02 | Kalshi UUID bet scaffold — mint every order as a GYST UUIDv8 and submit fast via kalshi_python SDK |
| `liquidity_hunter.py` | 2026-08-08 | Liquidity-aware Kalshi hunter — only trades on real depth, uses proven order path. |
| `liquidity_trader.py` | 2026-08-11 | liquidity_trader.py |
| `maker_engine.py` | 2026-08-02 | Maker engine — zero-fee resting bids below mid on KXBTC15M in calm tape, GTD self-expiring quotes, inventory cap, sells into strength; structural spread capture; … |
| `micro_grind_cycler.py` | 2026-08-12 | Micro-grind cycler: monitors settled positions, recycles freed capital |
| `micro_trader.py` | 2026-08-07 | Aggressive micro trader — drift entries, +15c/-10c exits, fee-aware, direct Kalshi V2. |
| `moonshot_engine.py` | 2026-08-03 | Moonshot sleeve — adjustable % of equity (default 25%) deployed in SIZED shots: cheap tails 10x+ payoff + strong-drift conviction plays; sleeve-isolated from the … |
| `panic_fade.py` | 2026-08-10 | Panic fade detector — buys when price drops >10¢ in one poll cycle |
| `parallel_play.py` | 2026-08-02 | $10 parallel volatile play — momentum sleeve (crypto 15M by 24h drift) + longshot lottery basket + LAD add, all verified against exchange acks |
| `parallel_play2.py` | 2026-08-02 | $10 parallel play v2 — fixed feeds (Kraken drift, ticker-direct fetch), momentum + longshot + mid sleeves, every fill verified vs ack fill_count |
| `parlay_loop.py` | 2026-08-03 | Parlay loop — fixed-% bankroll allocation fanned wide across all Kalshi combo families (2-10c tails), profits loop back to cash and compound; caps + kill-switch +… |
| `profit_loop.py` | 2026-08-02 | Autonomous profit loop — crypto 15M drift-momentum entries early-window only, parlay compounding (winners size up), settle write-back, bankroll guard |
| `profit_scalp.py` | 2026-08-07 | Speed-run scalp engine — early-window drift entries + reprice exits at +15c (no settlement wait), exchange-truth state, micro size, bankroll guard |
| `safe_grind.py` | 2026-08-12 | Minimal Kalshi micro-grinder using the official SDK only. |
| `speed_lane.py` | 2026-08-03 | $1 speed lane — max churn: cheap momentum entries (<=12c) on 15M windows, exit at +3c or settle, fastest cycle; argv SERIES PAIR; hard $1 budget; zero tokens |
| `trend_engine.py` | 2026-08-04 | Parameterized 15M trend engine — one script, any series: argv = SERIES KRAKEN_PAIR; Kraken-proven drift signal + tape momentum, both-side exits, own lock; the fan… |
| `universal_live_scanner.py` | 2026-08-07 | Universal live scanner — trades any market with real fills, no hardcoded tickers. |

## C — Signals & discovery  (16)

| Tool | Modified | Purpose |
|---|---|---|
| `airfare_engine.py` | 2026-08-10 | airfare_engine.py |
| `arb_scanner.py` | 2026-08-10 | Cross-venue arbitrage scanner — checks for price gaps between Kalshi and |
| `btc15m_probe.py` | 2026-08-15 | BTC-15m market-energy probe. Read-only except it prints everything needed |
| `calendar_engine.py` | 2026-08-03 | Calendar engine — scan all Kalshi markets closing <6h with real volume, compute snapshot momentum (own 5-min price history), micro-bet the movers 1ct at a time; z… |
| `continuous_liquidity_scanner.py` | 2026-08-08 | Continuous Kalshi liquidity scanner — polls 200 markets every 10s, trades on real depth. |
| `depth_scanner.py` | 2026-08-14 | Depth scanner: scan all open Kalshi markets for real orderbook depth. |
| `market_scanner.py` | 2026-08-10 | market_scanner.py |
| `news_supply_engine.py` | 2026-08-11 | News->supply-chain->market prediction engine — expanded 30-feed global RSS, supply-chain node mapping, bold forecasts minted as 0x326 FORECAST UUIDs, edge-gap ale… |
| `orderbook_monitor.py` | 2026-08-08 | Real-time Kalshi orderbook monitor — polls 200 markets, shows live depth, alerts on movement. |
| `poly_news_engine.py` | 2026-08-11 | Polymarket news/events/signals ingestor — Gamma API keyless reader that mints 0x3D6 SIGNAL UUIDs into the local stream; zero tokens |
| `poly_signal.py` | 2026-08-07 | Polymarket signal source for live trading fallback. |
| `shadow_index.py` | 2026-08-11 | Shadow index — tracked people/flows (Polymarket whale prints keyless, politician/trader registry) minted as 0x3D2 SHADOW UUIDs into the stream; runs parallel with… |
| `uptick_spiral.py` | 2026-08-11 | Uptick spiral — closes the feedback loop: scores past news forecasts against actual Kalshi market resolutions, adjusts supply-chain node weights (uptick for hits,… |
| `whale_copier.py` | 2026-08-11 | Whale copier — aggregate Polymarket trades per wallet, rank top whales by flow, copy their fresh prints to mapped Kalshi crypto windows with size scaled to convic… |
| `whale_follower.py` | 2026-08-10 | Whale follower daemon — polls Kalshi markets for whale-sized volume spikes |
| `x_watcher.py` | 2026-08-11 | X watcher v3 — expanded multi-query sentiment sweep with faster polling; official X API (bearer) with keyless fallback; zero tokens |

## D — Paper & simulation  (5)

| Tool | Modified | Purpose |
|---|---|---|
| `btc_paper_engine.py` | 2026-08-08 | BTC short paper-test engine — simulates short trades against live BTC spot, logs P&L. |
| `dry_run.py` | 2026-08-06 | Massive parallel paper engine — all 5 crypto 15M series, up to 3 open per series, simulated taker fills from real books, scalp+settle exits, hypothetical P&L repo… |
| `dry_run_no_cheap.py` | 2026-08-06 | dry_run_no_cheap.py — paper lane: NO entries only when drift<0 and price<=35c. |
| `paper_venue.py` | 2026-08-10 | Paper venue — internal matching engine fed by REAL Kalshi prices. |
| `propose_ticks.py` | 2026-09-10 | propose_ticks.py — paper-side Kalshi micro-tick proposer. |

## E — Execution & exits  (9)

| Tool | Modified | Purpose |
|---|---|---|
| `auto_exit.py` | 2026-08-14 | Auto exit: scan positions, find any executable depth, close immediately. |
| `kalshi_execute.py` | 2026-08-13 | Unified Kalshi execution path with real depth validation. |
| `kalshi_executor.py` | 2026-08-14 | kalshi_executor.py — GO-gated execution path for the /loop uptick monitor. |
| `micro_executor.py` | 2026-08-14 | Micro executor: execute cheap YES buys when depth is available. |
| `order_router.py` | 2026-08-10 | Order router — handles order placement, cancellation, and routing. |
| `poly_executor.py` | 2026-08-03 | Polymarket CLOB executor — armed daemon: reads wallet USDC on-chain; when funded, derives creds, sets allowances once, and mirrors the whale-copier's signals onto… |
| `positions_exit.py` | 2026-08-13 | Exit Kalshi positions at best executable ask price. |
| `trading_engine.py` | 2026-08-10 | Event-driven trading engine core. |
| `venue_router.py` | 2026-08-08 | Multi-venue liquidity router — chooses Kalshi or Polymarket based on real depth. |

## F — Ops, monitoring & reporting  (29)

| Tool | Modified | Purpose |
|---|---|---|
| `agent_status.py` | 2026-08-03 | Agent status publisher — aggregates fleet liveness, governor, equity, last commit, and data/agent_now.md into mc_state hermes:status every 60s; time.somacosf.com … |
| `cash_extract.py` | 2026-08-13 | Extract Kalshi live balance to a local file. |
| `cash_extractor.py` | 2026-08-11 | cash_extractor.py |
| `cycle_daemon.py` | 2026-08-07 | Kalshi 24h cycle daemon — 5-min position scan, hourly summary. |
| `evidence_engine.py` | 2026-08-03 | Evidence engine — the system that backs the claim: per-lane rolling win-rate with Wilson CI, expectancy per trade, live-vs-paper slippage, pre-registered PROVEN/F… |
| `failure_harness.py` | 2026-08-11 | Event-feed/trade failure harness — detects dead event feed, dead trading daemons, and dead MC; auto-restarts and logs failure signatures |
| `finance_tally.py` | 2026-08-02 | Financial tally — Kalshi equity decomposition (cash, positions by sleeve), day flows, allocation report |
| `fleet_watcher.py` | 2026-08-07 | fleet_watcher.py — close-in loop watchdog for the prediction-market fleet. |
| `funding_feed.py` | 2026-08-06 | Self-funding feed — watches configured wallets (Polygon/Base) for inbound USDC slurps via balance-delta detection; every slurp mints a 0x3D6 FUNDING UUIDv8 event … |
| `invest_api.py` | 2026-08-13 | Self-contained invest API data provider. |
| `lanes_report.py` | 2026-08-02 | Lanes of returns — per-engine P&L decomposition (momentum / parlay / sports / news lanes) from the ledger + exchange truth; zero tokens |
| `live_smoke_test.py` | 2026-08-11 | Live Kalshi smoke test — checks balance, scans open markets, and submits one small order when edge is present |
| `pocket_analysis.py` | 2026-08-03 | Where does the engine actually win — settle outcomes by series/side/entry-band from the ledger; the concentration map; zero tokens |
| `positions_dashboard.py` | 2026-08-13 | Standalone positions dashboard with manual exit. |
| `promoter.py` | 2026-08-03 | Dry-winner promoter — every 30min scans 24h of runlog dry-lane events, computes per-variant win rate + realized, crowns the highest-expectancy lane (n>=10), write… |
| `quick_status.py` | 2026-08-12 | — |
| `recovery_engine.py` | 2026-08-04 | Stuck-capital recovery — liquidates dead event positions at live bid, recovers cash, hands it to the guarded scalp loop. Fee-safe: only sells; never pays entry fees. |
| `run_report.py` | 2026-08-02 | Zero-token full-run reconstruction — reads JSONL run log + Supabase ledger + exchange truth, prints the entire session story in detail |
| `self_check.py` | 2026-08-02 | Full system self-check — fleet liveness, exchange auth/state, ledger truth, runlog assertions, stream freshness, git state; one call, zero tokens |
| `server_status.py` | 2026-08-03 | Single-page :8888 'where we are' status/explainer for the GYST UUID prediction-market engine |
| `server_view.py` | 2026-08-10 | scripts/server_view.py |
| `settlement_watcher.py` | 2026-08-10 | Settlement watcher daemon — polls all open positions and alerts when |
| `six_month_monitor.py` | 2026-08-06 | six_month_monitor.py — passive 6-month watcher. |
| `sweep_watch.py` | 2026-08-03 | Venmo sweep watcher — alerts when Kalshi cash >= TRIGGER ($140) to sweep $40 to Venmo; tracks sweep state + history in mc_state; zero tokens |
| `update_mc_state.py` | 2026-08-08 | Update mc_state with live Kalshi portfolio data. |
| `uptick_loop.py` | 2026-08-14 | /loop UPTICK monitor — runs autonomously, never trades. |
| `volume_watchdog.py` | 2026-08-12 | Volume watchdog for Kalshi markets. |
| `watchdog.py` | 2026-08-07 | — |
| `wti_settlement_watch.py` | 2026-08-11 | WTI hourly settlement watcher. |

## G — Data, ledger & UUID infrastructure  (21)

| Tool | Modified | Purpose |
|---|---|---|
| `download.sh` | 2026-06-08 | !/bin/bash |
| `gyst_master.py` | 2026-08-03 | Unified Python implementation of GYST UUIDv8 Protocol + TurboQuant |
| `kalshi_ws.py` | 2026-08-03 | Kalshi WS firehose — official wss v2 ticker stream for the 15M windows, written to the local tape (source=kalshi-ws) so engines see sub-second exchange-native mom… |
| `ledger_schema.sql` | 2026-08-02 | UUID-native trading ledger — every order/fill/settlement is a GYST UUIDv8; spawn-tree P&L by parent_uuid walk; reconciliation via low-42 bitmask |
| `pg_trades_backfill.py` | 2026-08-03 | scripts/pg_trades_backfill.py |
| `pg_trades_backfill_parallel.py` | 2026-08-03 | scripts/pg_trades_backfill_parallel.py |
| `pipe_a_to_b.py` | 2026-08-03 | Build B from A: derive compliant GYST spawn-model tables from flat uuid_trades (A untouched, idempotent pipe) |
| `proof_ledger.py` | 2026-08-02 | Transaction-level proof for the UUID trading ledger — order->fills->reconcile->settle->P&L, inside a rolled-back transaction (no DB pollution) |
| `proof_transaction.py` | 2026-08-03 | Transaction-level proof harness for GYST UUIDv8 engine (encode->store->bitmask-route->decode) |
| `runlog.py` | 2026-08-02 | Shared zero-token run logger — structured JSONL events + inline assertions, date-rotated, readable by any agent/tool without model tokens |
| `sb.py` | 2026-08-03 | Supabase PG connection helper — reads .env_turso (gitignored), returns psycopg2 conn to the cloud trading-ledger SoT. NEVER prints secrets. |
| `stream_mint_backfill.py` | 2026-08-03 | scripts/stream_mint_backfill.py |
| `supabase_schema.sql` | 2026-07-30 | — |
| `sync_supabase_subset.py` | 2026-08-03 | scripts/sync_supabase_subset.py |
| `turso_backfill.py` | 2026-08-03 | scripts/turso_backfill.py |
| `turso_trades_backfill.py` | 2026-08-03 | scripts/turso_trades_backfill.py |
| `uuid_ingest.py` | 2026-08-02 | Signal ingest — mint every raw tick (Kalshi book mid + crypto spot) as a GYST UUID into a local stream store; deterministic dedupe; algos consume UUIDs not JSON |
| `uuid_service_turboquant.py` | 2026-08-02 | Python mirror of the canonical TypeScript GYST UUIDv8 encoder |
| `uuid_zst_uuid.py` | 2026-08-03 | 1. Open Zstandard streaming reader |
| `verify_encoder.py` | 2026-08-02 | Determinism + round-trip verification for the GYST UUIDv8 encoder (uuid_service_turboquant). Reusable post-patch check. |
| `ws_feed.py` | 2026-08-10 | WebSocket feed for Kalshi market data. |

## H — Utility one-offs (`_*` debug/probe scripts)  (40)

| Tool | Modified | Purpose |
|---|---|---|
| `_apply_mc_state.py` | 2026-08-02 | CREATE TABLE IF NOT EXISTS mc_state ( |
| `_apply_schema.py` | 2026-08-03 | — |
| `_apply_schema_sb.py` | 2026-08-03 | — |
| `_backfill_no_trade.py` | 2026-08-02 | — |
| `_bench_wirespeed.py` | 2026-08-03 | Microbenchmark: is the GYST UUID actually a wirespeed maths-check substrate? |
| `_btc15_outcome.py` | 2026-08-02 | SELECT uuid, ticker, side, price_cents, status, exchange_order_id |
| `_btc15_probe.py` | 2026-08-02 | — |
| `_check_sb_subset.py` | 2026-08-03 | — |
| `_cross_mint.py` | 2026-08-03 | — |
| `_debug_fills.py` | 2026-08-02 | — |
| `_debug_turso.py` | 2026-08-03 | Debug: capture full Turso pipeline error body for a single insert. |
| `_find_pooler.py` | 2026-08-02 | — |
| `_first_fire.py` | 2026-08-02 | Prints order/ack/fill data only. Never prints key material. |
| `_get_pooler.py` | 2026-08-02 | — |
| `_get_sb_conn.py` | 2026-08-03 | connection string endpoint |
| `_income_check.py` | 2026-08-02 | — |
| `_income_round2.py` | 2026-08-02 | 1) ledger write-back: settle the 4 winning positions (result=yes => settle at 100) |
| `_mc_smoke.py` | 2026-08-03 | — |
| `_pem_check.py` | 2026-08-02 | — |
| `_probe_pg.py` | 2026-08-03 | — |
| `_probe_sb2.py` | 2026-08-03 | — |
| `_probe_supabase.py` | 2026-08-03 | Read .env_turso for SUPABASE_TOKEN |
| `_probe_trades.py` | 2026-08-03 | build token map |
| `_reconcile_play.py` | 2026-08-02 | — |
| `_run_supabase_sync.py` | 2026-08-03 | — |
| `_run_sync_bg.py` | 2026-08-03 | — |
| `_sb_check2.py` | 2026-08-03 | — |
| `_scan_btc15.py` | 2026-08-02 | — |
| `_scan_markets.py` | 2026-08-02 | — |
| `_scan_series.py` | 2026-08-02 | — |
| `_scan_vol.py` | 2026-08-02 | — |
| `_sdk_inspect.py` | 2026-08-03 | — |
| `_settle_check.py` | 2026-08-02 | — |
| `_test_bitmask_sql.py` | 2026-08-03 | — |
| `_test_sb_conn.py` | 2026-08-03 | — |
| `_track_fill.py` | 2026-08-02 | — |
| `_truth_no_order.py` | 2026-08-02 | — |
| `_vercel_env.py` | 2026-08-03 | set env vars (non-interactive: pipe value to `vercel env add`) |
| `_verify_mirror.py` | 2026-08-02 | — |
| `test_new_api.py` | 2026-08-12 | NEW Kalshi API endpoint |

## I — Shell / PowerShell launchers  (6)

| Tool | Modified | Purpose |
|---|---|---|
| `hermes-route-config.ps1` | 2026-09-09 | Configures Hermes model routing for a $21 Nous Portal balance |
| `install-tools.sh` | 2026-06-08 | !/bin/bash |
| `install_watchdog.ps1` | 2026-08-02 | Install the SoMaCo fleet watchdog via schtasks.exe — supervisor starts at logon + 5-min restart-if-dead task (atomic lock makes dupes harmless) |
| `provision_vps.sh` | 2026-08-03 | Provision a Linux VPS (Hetzner/omen-02-Linux) for the SoMaCo fleet — uv venv, deps, systemd supervisor unit; zero tokens |
| `relaunch_fleet.ps1` | 2026-08-04 | Post-reboot fleet + deploy helper. Confirms the auto-started fleet, and provides a RAM-safe Vercel deploy that does NOT OOM (sets Node old-space to 8GB). Run from… |
| `start_pg.bat` | 2026-07-30 | — |

## scripts/strategies — pluggable strategy modules  (5)

| File | Modified | Purpose |
|---|---|---|
| `scripts/strategies/__init__.py` | 2026-08-10 | Panic fade strategy — buys after >10¢ drops when bid is still >20¢. |
| `scripts/strategies/airfare_tuesday.py` | 2026-08-10 | airfare_tuesday.py |
| `scripts/strategies/arb.py` | 2026-08-10 | Arbitrage strategy — intra-market arb when YES+NO combined < $0.99. |
| `scripts/strategies/panic_fade.py` | 2026-08-10 | Panic fade strategy — buys after >10¢ drops when bid is still >20¢. |
| `scripts/strategies/whale_follow.py` | 2026-08-10 | Whale follow strategy — follows large volume spikes and price moves. |

## app/ — Next.js dashboard (mc.somacosf.com)  (48)

| File | Modified | Purpose |
|---|---|---|
| `app/lib/_cross_mint.mjs` | 2026-08-02 | — |
| `app/lib/auth.js` | 2026-07-30 | — |
| `app/lib/status.js` | 2026-07-30 | — |
| `app/lib/trade-db.js` | 2026-08-02 | Supabase PG pool for the trade mission control (shared ledger SoT) |
| `app/lib/trade-kalshi.js` | 2026-08-03 | Kalshi V2 REST signing + order placement (RSA-PSS) for the trade mission control |
| `app/lib/trade-mc.js` | 2026-08-02 | Shared mission-control helpers — passkey check, kill state + event log in Supabase (serverless-safe) |
| `app/lib/trade-uuid.js` | 2026-08-02 | Byte-exact JS port of the GYST UUIDv8 encoder (uuid_service_turboquant.py) + trading mints — identical UUIDs across Python/JS |
| `app/lib/trade-uuid.mjs` | 2026-08-02 | Byte-exact JS port of the GYST UUIDv8 encoder (uuid_service_turboquant.py) + trading mints — identical UUIDs across Python/JS |
| `app/next.config.js` | 2026-08-10 | — |
| `app/pages/api/activity.js` | 2026-07-30 | Activity endpoint — serves last-known action state (refreshed on deploy) |
| `app/pages/api/btc/summary.js` | 2026-08-08 | BTC paper-test summary API |
| `app/pages/api/info/cycle.js` | 2026-08-09 | Live daemon cycle tracker API |
| `app/pages/api/status.js` | 2026-07-30 | Public status endpoint (passkey gate removed, shareable) |
| `app/pages/api/time/articles.js` | 2026-08-02 | TIME articles — AI-topic feed from mc_state (published by the news engine) + vote counts |
| `app/pages/api/time/comments.js` | 2026-08-02 | TIME discussion — GET comments for an article, POST a new one (mc_log-backed, kind='time-comment') |
| `app/pages/api/time/forecasts.js` | 2026-08-03 | TIME forecasts — the news engine's supply-chain predictions with probabilities |
| `app/pages/api/time/markets.js` | 2026-08-02 | TIME markets — open Kalshi markets matching a topic keyword (the trade-on-the-news plane) |
| `app/pages/api/time/oracle.js` | 2026-08-03 | Oracle API — the pre-committed 15M calls: current call + scored history + hit rate |
| `app/pages/api/time/status.js` | 2026-08-03 | Agent status API — hermes:status (what the agent is doing, fleet, equity, commit) + governor state |
| `app/pages/api/time/vote.js` | 2026-08-02 | TIME voting — POST {id, dir} increments the article/topic vote counter in mc_state |
| `app/pages/api/trade/bridge.js` | 2026-08-04 | Bridge API — cross-account funding awareness: Kalshi cash + Poly USDC + the current recommendation and message. |
| `app/pages/api/trade/control.js` | 2026-08-02 | Kill switch + event log endpoints (passkey-gated writes) |
| `app/pages/api/trade/daemons.js` | 2026-08-11 | Rich daemon beats — heartbeat age, what each watches, uptime, last action from mc_state + heartbeat files |
| `app/pages/api/trade/dry.js` | 2026-08-02 | Dry-run state API — paper engine state from mc_state + recent dry events from mc_log |
| `app/pages/api/trade/edge.js` | 2026-08-11 | Edge finder — compares model probabilities to live Kalshi market prices to find where betting makes more |
| `app/pages/api/trade/equity.js` | 2026-08-03 | Equity history API — the account curve (equity_history written by fill_poller) |
| `app/pages/api/trade/events.js` | 2026-08-11 | Live event feed — aggregates all signal sources from mc_state |
| `app/pages/api/trade/evidence.js` | 2026-08-03 | Evidence API — the engine's verdicts (win-rate CI, expectancy, PROVEN/FORMING/DEAD) from mc_state |
| `app/pages/api/trade/fleet.js` | 2026-08-02 | Fleet health API — daemon heartbeats from mc_state (daemon:* keys) + ages |
| `app/pages/api/trade/funds.js` | 2026-08-06 | FUNDS API — the money truth across both venues: equity/cash/marks/realized, per-lane returns, vault, moonshot sleeve, sweep state, Polymarket signal flow |
| `app/pages/api/trade/lanes.js` | 2026-08-03 | Lanes API — fleet health + per-lane open/realized decomposition for the dashboard |
| `app/pages/api/trade/ledger.js` | 2026-08-02 | Ledger read views — orders/fills/positions/pnl/acks in one endpoint |
| `app/pages/api/trade/markets.js` | 2026-08-02 | Live Kalshi markets proxy (public, dollar/fixed-point schema) |
| `app/pages/api/trade/order.js` | 2026-08-02 | Order endpoint — passkey-gated PAPER/LIVE fire with caps, kill switch, UUID mint, ACK child, ledger writes |
| `app/pages/api/trade/poly.js` | 2026-08-03 | Polymarket panel API — whale flow (shadow), divergences (xvenue), wallet leaderboard (copier), top poly markets |
| `app/pages/api/trade/positions.js` | 2026-08-03 | Positions API — open positions + realized from the ledger (uuid_positions) |
| `app/pages/api/trade/settles.js` | 2026-08-03 | Settles API — REAL wins/losses from the ledger (uuid_positions realized P&L) |
| `app/pages/api/trade/shadow.js` | 2026-08-02 | Shadow index API — latest shadow signals (whale prints) from the local stream via mc_state publish |
| `app/pages/api/trade/stats.js` | 2026-08-02 | Mission control stats — ledger counts, P&L, kill, keys (Supabase) |
| `app/pages/api/trade/status.js` | 2026-08-03 | Status API — the real-time logic proof: LIVE vs PAPER split, pipeline chain freshness, fleet, computed PASS/FAIL checks |
| `app/pages/api/trade/tim_bets.js` | 2026-08-02 | Tim bet history — recent live orders with ack/settle status from the ledger |
| `app/pages/api/trade/tim_order.js` | 2026-08-03 | Tim's order route — PIN-gated (TIM_PIN env), hard caps ($2/order, $20/day), ledger-minted via the same V2 path |
| `app/pages/btc.js` | 2026-08-08 | — |
| `app/pages/grind.js` | 2026-08-09 | — |
| `app/pages/index.js` | 2026-07-30 | — |
| `app/pages/info.js` | 2026-08-10 | — |
| `app/pages/time.js` | 2026-08-10 | — |
| `app/scripts/collect_status.js` | 2026-07-30 | — |

## src/ — research & analysis package (Kalshi/Polymarket studies)  (56)

| File | Modified | Purpose |
|---|---|---|
| `src/__init__.py` | 2026-06-08 | — |
| `src/analysis/__init__.py` | 2026-06-08 | — |
| `src/analysis/comparison/__init__.py` | 2026-06-08 | — |
| `src/analysis/comparison/win_rate_by_price_animated.py` | 2026-06-08 | Animated side-by-side calibration comparison between Kalshi and Polymarket. |
| `src/analysis/kalshi/__init__.py` | 2026-06-08 | — |
| `src/analysis/kalshi/ev_yes_vs_no.py` | 2026-06-08 | Compare expected value of YES vs NO bets at each price level. |
| `src/analysis/kalshi/kalshi_calibration_deviation_over_time.py` | 2026-06-08 | Plot Kalshi calibration deviation over time. |
| `src/analysis/kalshi/longshot_volume_share_over_time.py` | 2026-06-08 | Analyze longshot volume share evolution over time. |
| `src/analysis/kalshi/maker_returns_by_direction.py` | 2026-06-08 | Analyze maker returns by position direction (YES vs NO). |
| `src/analysis/kalshi/maker_taker_gap_over_time.py` | 2026-06-08 | Analyze maker-taker gap evolution over time. |
| `src/analysis/kalshi/maker_taker_returns_by_category.py` | 2026-06-08 | Analyze maker vs taker returns by market category. |
| `src/analysis/kalshi/maker_vs_taker_returns.py` | 2026-06-08 | Analyze maker vs taker returns. |
| `src/analysis/kalshi/maker_win_rate_by_direction.py` | 2026-06-08 | Analyze maker win rate by position direction (YES vs NO). |
| `src/analysis/kalshi/market_types.py` | 2026-06-08 | Analyze distribution of market types by volume with hierarchical groupings. |
| `src/analysis/kalshi/meta_stats.py` | 2026-06-08 | Generate meta statistics for the dataset. |
| `src/analysis/kalshi/mispricing_by_price.py` | 2026-06-08 | Analyze mispricing percentage by contract price for takers, makers, and combined. |
| `src/analysis/kalshi/returns_by_hour.py` | 2026-06-08 | Analyze excess returns by hour of day (ET). |
| `src/analysis/kalshi/statistical_tests.py` | 2026-06-08 | Comprehensive statistical tests for paper claims. |
| `src/analysis/kalshi/trade_size_by_role.py` | 2026-06-08 | Analyze trade size distribution by role (maker vs taker). |
| `src/analysis/kalshi/util/__init__.py` | 2026-06-08 | Utility modules for analysis. |
| `src/analysis/kalshi/util/categories.py` | 2026-06-08 | Category grouping utilities for market analysis with hierarchical structure. |
| `src/analysis/kalshi/volume_over_time.py` | 2026-06-08 | Analyze trading volume over time across all Kalshi markets. |
| `src/analysis/kalshi/vwap_by_hour.py` | 2026-06-08 | Analyze volume-weighted average price by hour of day (ET). |
| `src/analysis/kalshi/win_rate_by_price.py` | 2026-06-08 | Analyze win rate by price to assess market calibration. |
| `src/analysis/kalshi/win_rate_by_trade_size.py` | 2026-06-08 | Analyze win rate by trade size with confidence intervals. |
| `src/analysis/kalshi/yes_vs_no_by_price.py` | 2026-06-08 | Analyze YES/NO preference by price, comparing takers vs makers. |
| `src/analysis/polymarket/__init__.py` | 2026-06-08 | — |
| `src/analysis/polymarket/polymarket_calibration_by_bucket.py` | 2026-06-08 | Polymarket calibration analysis grouped by probability buckets. |
| `src/analysis/polymarket/polymarket_trades_over_time.py` | 2026-06-08 | Analyze Polymarket trade counts over time at block-level granularity. |
| `src/analysis/polymarket/polymarket_volume_over_time.py` | 2026-06-08 | Analyze Polymarket notional trading volume over time. |
| `src/analysis/polymarket/polymarket_win_rate_by_price.py` | 2026-06-08 | Analyze Polymarket win rate by price to assess market calibration. |
| `src/common/__init__.py` | 2026-06-08 | — |
| `src/common/analysis.py` | 2026-06-08 | Base class for analyses that generate figures and data outputs. |
| `src/common/client.py` | 2026-06-08 | Check if an exception should trigger a retry. |
| `src/common/gyst.py` | 2026-07-30 | Unified Python implementation of GYST UUIDv8 Protocol + TurboQuant |
| `src/common/indexer.py` | 2026-06-08 | Base class for data indexers that fetch and store market data. |
| `src/common/interfaces/__init__.py` | 2026-06-08 | — |
| `src/common/interfaces/chart.py` | 2026-06-08 | Python types for generating valid ResearchChart configurations. |
| `src/common/storage.py` | 2026-06-08 | Get all market chunk files sorted by start index. |
| `src/common/util/__init__.py` | 2026-06-08 | — |
| `src/common/util/package.py` | 2026-06-08 | Package the data directory into a zstd-compressed tar archive. |
| `src/common/util/strings.py` | 2026-06-08 | Convert snake_case string to Title Case. |
| `src/indexers/__init__.py` | 2026-06-08 | — |
| `src/indexers/kalshi/__init__.py` | 2026-06-08 | — |
| `src/indexers/kalshi/client.py` | 2026-06-08 | Make a GET request with retry/backoff. |
| `src/indexers/kalshi/markets.py` | 2026-06-08 | Indexer for Kalshi markets data. |
| `src/indexers/kalshi/models.py` | 2026-06-08 | Normalize microseconds to 6 digits |
| `src/indexers/kalshi/trades.py` | 2026-06-08 | Indexer for Kalshi trades data. |
| `src/indexers/polymarket/__init__.py` | 2026-06-08 | — |
| `src/indexers/polymarket/blockchain.py` | 2026-06-08 | Fetch Polymarket trades directly from the Polygon blockchain. |
| `src/indexers/polymarket/blocks.py` | 2026-06-08 | Indexer for block timestamps from the Polygon blockchain. |
| `src/indexers/polymarket/client.py` | 2026-06-08 | Make a GET request with retry/backoff. |
| `src/indexers/polymarket/fpmm_trades.py` | 2026-06-08 | Indexer for Polymarket FPMM trades from the Polygon blockchain. |
| `src/indexers/polymarket/markets.py` | 2026-06-08 | Indexer for Polymarket markets data. |
| `src/indexers/polymarket/models.py` | 2026-06-08 | — |
| `src/indexers/polymarket/trades.py` | 2026-06-08 | Indexer for Polymarket trades from the Polygon blockchain. |

## swarm_watcher/ — Up/Down Signal Swarm corpus builder (local)  (8)

| File | Modified | Purpose |
|---|---|---|
| `swarm_watcher/__init__.py` | 2026-08-15 | Up/Down Signal Swarm watcher — local corpus builder. |
| `swarm_watcher/corpus_view.py` | 2026-08-15 | swarm_watcher.corpus_view |
| `swarm_watcher/demo.py` | 2026-08-15 | swarm_watcher.demo |
| `swarm_watcher/engine.py` | 2026-08-15 | swarm_watcher.engine |
| `swarm_watcher/gyst_codes.py` | 2026-08-15 | swarm_watcher.gyst_codes |
| `swarm_watcher/math_core.py` | 2026-08-15 | swarm_watcher.math_core |
| `swarm_watcher/store.py` | 2026-08-15 | swarm_watcher.store |
| `swarm_watcher/tests_math.py` | 2026-08-15 | Tests for swarm_watcher.math_core + gyst_codes + store. |

## stream-view/ — Rust stream viewer  (1)

| File | Modified | Purpose |
|---|---|---|
| `stream-view/src/main.rs` | 2026-08-11 | — |

## tests/ — test suite  (5)

| File | Modified | Purpose |
|---|---|---|
| `tests/conftest.py` | 2026-06-08 | Shared fixtures for analysis tests. |
| `tests/test_analysis_run.py` | 2026-06-08 | Test that every analysis run() produces valid output. |
| `tests/test_analysis_save.py` | 2026-06-08 | Test Analysis.save() in isolation with mock outputs. |
| `tests/test_backfill_cursor.py` | 2026-06-08 | Test that backfill can be interrupted with Ctrl+C and resumed. |
| `tests/test_compile.py` | 2026-06-08 | Verify all source modules compile, import cleanly, and can be instantiated. |

## Root tools  (4)

| File | Modified | Purpose |
|---|---|---|
| `app.py` | 2026-08-02 | Prints high-level account status across all integrated platforms. |
| `main.py` | 2026-06-08 | Run analysis by name or show interactive menu. |
| `run_engine.py` | 2026-08-02 | Triggers on fill (0x3A7). Spawns a child exit ask (0x3A5) at fill + 15 cents. |
| `server.py` | 2026-07-30 | — |

## Backups & archives (17 + 1 archive dir)

House pattern: `.bk` copies kept beside originals; archived backfills under `scripts/__archive__/`.

- `app/next.config.js.bk`
- `app/public/trade/about.html.bk_20260811`
- `app/public/trade/index.html.bk_20260811`
- `data/cash_extractor_state.json.bk`
- `data/liquidity_trader_state.json.bk`
- `data/market_scan.jsonl.bk`
- `scripts/__archive__/turso_backfill.py.bk_20260730_123233`
- `scripts/__archive__/turso_backfill.py.bk_20260730_131129`
- `scripts/__archive__/turso_backfill.py.bk_20260730_132600`
- `scripts/fill_poller.py.bk`
- `scripts/fixed_hunter.py.bk`
- `scripts/fleetlib.py.bk`
- `scripts/kalshi_uuid_bot.py.bk`
- `scripts/profit_scalp.py.bk`
- `scripts/supervisor.py.bk`
- `scripts/uuid_service_turboquant.py.bk`
- `scripts/uuid_service_turboquant.py.bk2`

## Live artifacts observed (logs/ — last-run evidence, not liveness proof)

- Locks: `.fixed_hunter.lock`, `.volume_watchdog.lock`, `dry-t10.lock`, `dry-t20.lock`, `dry-t25.lock`, `mc.lock`
- Heartbeats present: `agent-status, bridge, btctrend, calendar, copier, dry, evidence, fills, funding, governor, ingest, maker` (+more)
- 124 entries in `logs/`. Current operational truth: check `data/uptick.log` + `data/executor.log`.

---
*Generated by static scan; descriptions as-written in file headers. Fleet roles/status: `FLEET_ARCHITECTURE.md` + fleet-ops skill.*