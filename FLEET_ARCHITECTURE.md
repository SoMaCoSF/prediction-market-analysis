# SoMaCo Trade Control — Fleet Architecture

> Living document. Last updated: 2026-08-11. Source of truth: this repo + the running fleet on OMEN-01.

## What This Is

An autonomous prediction-market trading engine operating on **Kalshi** (CFTC-regulated, live capital) and **Polymarket** (on-chain, dormant until wallet funded). The system runs 34+ Python daemons on a Windows host, supervised by a process manager, with a Vercel-hosted Next.js dashboard reading from a cloud Postgres ledger.

## System Topology

```
┌─────────────────────────────────────────────────────────────────┐
│  OMEN-01 (Windows, local)                                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  supervisor.py (pythonw.exe, headless)                   │   │
│  │    ├── mission_control.py    (mc)          CORE          │   │
│  │    ├── vault.py               (vault)      CORE          │   │
│  │    ├── kalshi_ws.py           (ws)          CORE          │   │
│  │    ├── tick_service.py        (tick)       CORE          │   │
│  │    ├── governor.py            (governor)   CORE          │   │
│  │    ├── oracle.py              (oracle)     CORE          │   │
│  │    ├── bridge_coordinator.py  (bridge)     CORE          │   │
│  │    ├── evidence_engine.py     (evidence)   OPS           │   │
│  │    ├── ingest.py              (ingest)     CORE          │   │
│  │    ├── recovery_engine.py     (recover)    OPS           │   │
│  │    │                                                        │   │
│  │    ├── profit_scalp.py       (scalp)      TRADING        │   │
│  │    ├── btc_trend.py           (btctrend)   TRADING        │   │
│  │    ├── trend_engine.py x4     (trend-*)    TRADING        │   │
│  │    ├── maker_engine.py        (maker)      TRADING        │   │
│  │    ├── crossvenue_engine.py   (xvenue)    TRADING        │   │
│  │    ├── promoter.py            (promoter)   TRADING        │   │
│  │    ├── poly_executor.py       (poly-exec) TRADING        │   │
│  │    ├── moonshot sleeve        (moonshot)   TRADING        │   │
│  │    ├── parlay tails           (parlay)     TRADING        │   │
│  │    ├── speed-btc/eth          (speed-*)   TRADING        │   │
│  │    │                                                        │   │
│  │    ├── x_watcher.py           (xwatch)    SIGNAL         │   │
│  │    ├── shadow_index.py        (shadow)    SIGNAL         │   │
│  │    ├── news_supply_engine.py  (news)      SIGNAL         │   │
│  │    ├── whale_copier.py        (copier)    SIGNAL         │   │
│  │    ├── uptick_spiral.py       (uptick)    SIGNAL         │   │
│  │    │                                                        │   │
│  │    ├── dry_run.py x4          (dry-*)     PAPER          │   │
│  │    │                                                        │   │
│  │    ├── sweep_watch.py         (sweep)     OPS            │   │
│  │    ├── calendar_engine.py     (calendar)  OPS            │   │
│  │    ├── funding_feed.py        (funding)   OPS            │   │
│  │    ├── agent_status.py        (agent-status) OPS         │   │
│  │    └── fill_poller.py         (fills)     CORE           │   │
│  └──────────────────────────────────────────────────────────┘   │
│      ↑ writes                    ↑ reads                         │
│  ┌────────────────┐         ┌────────────────┐                   │
│  │  SQLite (sb)   │         │  .env (keys)   │                   │
│  │  local state   │         │  Kalshi PEM    │                   │
│  └────────────────┘         └────────────────┘                   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Supabase PG (TCP)
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│  Supabase Postgres (cloud ledger — shared source of truth)      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ uuid_orders  │  │ uuid_fills   │  │ uuid_positions   │       │
│  │ uuid_× GYST  │  │ exchange     │  │ realized_pnl     │       │
│  └──────────────┘  └──────────────┘  └──────────────────┘       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐       │
│  │ equity_hist  │  │ mc_state     │  │ (trades, etc)    │       │
│  │ time series  │  │ key→value    │  │                  │       │
│  └──────────────┘  └──────────────┘  └──────────────────┘       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ PG pool (TRADE_DATABASE_URL)
                           ↓
┌──────────────────────────────────────────────────────────────────┐
│  Vercel (Next.js 14, mc.somacosf.com)                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  app/pages/api/trade/                                     │   │
│  │    stats.js     — equity, cash, P&L, kill, keys           │   │
│  │    fleet.js     — daemon heartbeats from mc_state         │   │
│  │    daemons.js   — rich daemon beats (roles, categories)   │   │
│  │    edge.js      — Kalshi MLB edge-finder (NEW)            │   │
│  │    markets.js   — live Kalshi market prices               │   │
│  │    lanes.js     — per-lane open/realized decomposition     │   │
│  │    evidence.js  — statistical edge validation             │   │
│  │    equity.js    — equity curve history                     │   │
│  │    settles.js   — realized wins/losses                     │   │
│  │    shadow.js    — whale flow signals                        │   │
│  │    positions.js — open positions table                      │   │
│  │    funds.js     — full funds truth (vault, dry, xvenue)    │   │
│  │    dry.js       — paper engine state                       │   │
│  │    order.js     — place live/paper orders                   │   │
│  │    status.js    — computed PASS/FAIL checks                │   │
│  │    poly.js      — Polymarket state                          │   │
│  │    tim_*.js     — guest betting surface                     │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  app/public/trade/index.html                              │   │
│  │    SOMACO TRADE CONTROL v4                                │   │
│  │    • Account equity hero + sparkline                       │   │
│  │    • Edge Finder (Kalshi MLB — model vs market)           │   │
│  │    • Daemon Beats (live heartbeats + what each watches)   │   │
│  │    • Engine lanes (fleet + per-lane returns)              │   │
│  │    • Evidence verdicts (PROVEN/DEAD/PENDING per lane)     │   │
│  │    • Live markets, settles, whale flow                    │   │
│  │    • Bet interface (15M window + order ticket)            │   │
│  │    • Positions & P&L                                      │   │
│  │    • Deep Dashboard (fleet, vault, dry-run, x-venue)      │   │
│  │    • Architecture docs (expandable)                        │   │
│  │    • Three.js icosphere backdrop (pulses on fills)        │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

## GYST UUIDv8 Substrate

Every order, fill, position, and settlement is identified by a 128-bit UUIDv8 with embedded:
- **Type code** (8 bits): order `0x121`, fill `0x130`, position `0x140`, etc.
- **Namespace** (16 bits): routing domain (e.g. `somacosf.com` = `0x55d`)
- **Timestamp** (48 bits): millisecond precision
- **Bitmask routing** (remaining bits): enables parallel mint without collision

This means IDs are globally unique, self-describing, and sortable by time — no auto-increment, no UUIDv4 random strings.

## Trading Lanes

| Lane | Ticker Pattern | Description | Status |
|------|---------------|-------------|--------|
| momentum-15M | `KXBTC15M`, `KXETH15M`, etc. | 15-minute crypto directional bets | Active |
| parlay-tails | `KXMV*` | Multi-game MLB composite bets | Active |
| sports | `KXMLBGAME-*` | Individual MLB game markets | Edge-finder live |
| supply-chain | `KXWTI*`, `KXCPI*` | Economic event markets | Signal-only |
| news | `KXNASDAQ*`, `KXSP500*` | Index event markets | Signal-only |

## Edge Finder (NEW)

The `/api/trade/edge` endpoint:
1. Fetches all open `KXMLBGAME` markets from Kalshi
2. Matches them to model predictions (win probabilities)
3. Fetches individual market order books for live bid/ask
4. Computes edge = `model_prob - market_price`
5. Returns sorted list with best edges first, including:
   - Best side (YES or NO)
   - Edge in cents per contract
   - ROI percentage
   - Direct Kalshi trade link

The dashboard renders this as a sortable table — click any row to open the Kalshi market.

## Daemon Fleet Details

### Process Model
- `supervisor.py` launches all daemons via `.venv311/Scripts/pythonw.exe` (headless, no console windows)
- Each daemon calls `acquire_lock()` from `fleetlib.py` — duplicates die at birth (singleton enforcement)
- Each daemon calls `checkin()` every loop iteration — stale heartbeat (>180s) triggers supervisor restart
- Heartbeats stored as `logs/<name>.heartbeat` (timestamp) and `mc_state` table (`daemon:<name>` = "alive")

### Why 71 pythonw processes for 34 daemons?
The uv venv's `pythonw.exe` (249KB) is a **launcher shim** that spawns the real uv-managed `cpython-3.11-windows-x86_64-none/pythonw.exe` as a child. Each daemon = 2 processes (shim + real). This is normal uv behavior on Windows, not a bug.

### Failure Harness
After two bluescreen crashes (bugcheck `0x124` — WHEA hardware PCIe fault, recurring), we built `/d/somacosf/scripts/failure_harness/`:
- `crash_capture.py` — reads WER event logs, detects bugcheck codes (0x124 = WHEA)
- `state_snapshot.py` — captures processes, fleet, git, disks, memory at crash time
- `recovery.py` — generates crash diagnosis + recommended recovery steps
- `session_logger.py` — structured logging with rotation and severity filtering
- `harness.py` — CLI: `watch`, `snapshot`, `recover`, `status`, `crashes`, `snapshots`
- `install.py` — installs as a scheduled task (runs every 5 min)
- 51/51 verification checks pass

## API Surface (Vercel)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/trade/stats` | GET | Equity, cash, P&L, kill switch, key status |
| `/api/trade/fleet` | GET | Daemon heartbeats (name, state, age) |
| `/api/trade/daemons` | GET | **NEW** — Rich daemon beats with roles + categories |
| `/api/trade/edge` | GET/POST | **NEW** — Kalshi MLB edge-finder |
| `/api/trade/markets` | GET | Top-volume live Kalshi markets |
| `/api/trade/lanes` | GET | Per-lane open/realized decomposition |
| `/api/trade/evidence` | GET | Statistical edge validation per lane |
| `/api/trade/equity` | GET | Equity curve history (sparkline) |
| `/api/trade/settles` | GET | Realized wins/losses |
| `/api/trade/shadow` | GET | Whale flow signals (not our money) |
| `/api/trade/positions` | GET | Open positions table |
| `/api/trade/funds` | GET | Full funds truth (vault, dry-runs, x-venue, moonshot) |
| `/api/trade/dry` | GET | Paper engine state |
| `/api/trade/order` | POST | Place live/paper order |
| `/api/trade/status` | GET | Computed PASS/FAIL system checks |
| `/api/trade/poly` | GET | Polymarket state |
| `/api/trade/control` | GET | Kill switch + auto-follow state |
| `/api/trade/tim_bets` | GET | Guest betting surface (Tim) |
| `/api/trade/tim_order` | POST | Guest order placement (hard caps) |

## Subdomains

| Domain | Serves | Purpose |
|--------|--------|---------|
| `mc.somacosf.com` | `/trade/index.html` | Mission control terminal (this dashboard) |
| `trade.somacosf.com` | `/trade/index.html` | Alias |
| `dry.somacosf.com` | `/dry/index.html` | Public paper-engine terminal |
| `tim.somacosf.com` | `/tim/index.html` | Guest phone betting (PIN-gated, $2/order, $20/day) |
| `time.somacosf.com` | `/time/index.html` | The AI Times magazine |
| `poly.somacosf.com` | `/poly/index.html` | Polymarket control panel |

## Capital State (as of 2026-08-11)

- **Kalshi**: ~$24.98 working bankroll, live trading active on 15M crypto
- **Polymarket**: wallet `0xbC6662be0803F28C827BC405477F0b5AB8c6Dd40` — unfunded (awaiting USDC on Polygon)
- **Floor**: $10 (MC blocks orders below this)
- **Sweep rule**: cash ≥ $200 → withdraw $100 to Venmo (no API — manual tap in Kalshi app)

## Key Files

| Path | Purpose |
|------|---------|
| `scripts/supervisor.py` | Fleet launcher — spawns all daemons headless |
| `scripts/fleetlib.py` | Singleton locks + heartbeat checkin |
| `scripts/mission_control.py` | Order routing, kill switch, floor guard |
| `scripts/uptick_spiral.py` | Forecast accuracy scoring (Brier score) |
| `scripts/news_supply_engine.py` | RSS/news ingestion for event signals |
| `app/lib/trade-db.js` | Supabase PG pool (Vercel side) |
| `app/lib/trade-kalshi.js` | Kalshi API client (key presence check) |
| `app/lib/trade-mc.js` | Kill switch state |
| `app/lib/trade-uuid.js` | GYST UUIDv8 minting (server-side) |
| `app/public/trade/index.html` | The dashboard (v4) |
| `app/next.config.js` | Subdomain routing (mc/trade/dry/tim/time/poly) |

## Verification Checklist

- [ ] `next build` passes locally
- [ ] `/api/trade/daemons` returns daemon list with roles
- [ ] `/api/trade/edge` returns Kalshi MLB edges with positive values
- [ ] Dashboard renders edge table + daemon grid
- [ ] Three.js backdrop loads without errors
- [ ] All existing sections still render (markets, settles, positions, evidence)
- [ ] `renderDeep()` populates all 6 deep dashboard panels
