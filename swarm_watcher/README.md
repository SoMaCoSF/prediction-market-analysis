# Up/Down Signal Swarm — Corpus Builder

> LOCAL-FIRST. No deploy. No public surface. Validated math, then we talk.

## The idea (user's words, paraphrased)
Follow the live up/down signals. You can see when certain wallets run a
**down-signal swarm** vs an **up-signal response** vs each other. Evaluate the
**ratio of ups vs downs per wallet**, find **who those wallets are**, detect
**bidding patterns**, graph it, and give each one a **GYST UUIDv8** in the
SoMaCoSF substrate.

## What this module does
`prediction-market-analysis/swarm_watcher/` is a local SQLite corpus builder:

1. **Ingest** up/down market actions attributed to wallets (`Action`).
2. **Evaluate** per-wallet up/down ratio (`bias ∈ [0,1]`), cross-wallet
   divergence, market-wide consensus, contrarian score, and temporal
   *stickiness* (does a wallet's direction persist or mean-revert?).
3. **Classify** each wallet into a swarm polarity (STRONG_UP / UP / NEUTRAL /
   DOWN / STRONG_DOWN) and a pattern (sticky vs contrarian).
4. **Mint GYST UUIDv8** — `0x3F0 TRADER_WALLET` for the wallet identity,
   `0x3F2 TRADER_SIGNAL` for the derived up/down swarm signal (signal field =
   bias).
5. **Persist** to a local SQLite DB (`wallets`, `ticks`, `signals`,
   `swarm_events`, `wallet_profiles`) for dashboards.

## Math (tested — see `tests_math.py`, 31 passing)
- `swarm_bias = up / (up + down)` — neutral 0.5, net-up → 1.0, net-down → 0.0.
- `swarm_divergence(a, b) = a − b` — directed: who pushes up relative to whom.
- `contrarian_score = (market_bias − wallet_bias) × 2` ∈ [−1,1].
- `stickiness = mean autocorrelation(lag 1..5)` of signed directional flow.
  +1 = persistent directional swarm; ~0 = random; negative = mean-reverting.
- `profile_all` returns a `WalletProfile` for every wallet vs the collective
  swarm, sorted by `|divergence_vs_market|` for the dashboard.

## GYST UUIDv8 layout (port of `lib/gyst.ts`, RFC-valid v8)
```
high64: type(12) | namespace(12) | timestamp(24) | version(4)=8 | fractal(12)
low64:  variant(2)=10 | provenance(4) | signal(16) | random(42)
```
- `type` top 12 bits: `0x3F0` wallet, `0x3F2` signal (matches substrate registry).
- `signal` field (16 bits) = `round(bias × 65535)` → decodable bias.
- Validated: `uuid.UUID(...).version == 8`, type decodes back to 0x3F0/0x3F2.

## Status
- ✅ Math core, store, GYST minting, engine — implemented + unit-tested.
- ✅ Synthetic demo (`python -m swarm_watcher.demo`) proves the corpus.
- ✅ 31/31 tests pass.
- ⏳ Live ingest from Kalshi/Polymarket is OPTIONAL and must be passed in as a
  generator the caller controls — the watcher never opens its own network.
- ⏳ Dashboard: local route stub only (no Vercel). See `DASHBOARD_PLAN.md`.

## How to run
```
cd prediction-market-analysis
.venv311/Scripts/python -m pytest swarm_watcher/tests_math.py -q
.venv311/Scripts/python -m swarm_watcher.demo
```
