<!-- =============================================================================== file_id: SOM-DOC-0914-v1.0.0 name: MASTER_PLAN.md description: Master organization + execution plan — protocol consolidation, UUID-native trading ledger, paper gate, real-money Kalshi/Polymarket P&L, says.com convergence project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [plan, master, pnl, kalshi, polymarket, protocol, organization] created: 2026-07-31 modified: 2026-07-31 version: 1.0.0 agent_id: FABLE-HERMES =============================================================================== -->

# MASTER PLAN — From Fragmented Research to Deployed Protocol + Real P&L

**Owner:** Phoenix / SoMaCoSF   **Author:** Fable (full-corpus context: 102 gists, 394-row corpus, live engine)
**Companion artifacts:** `infographic/index.html` (SOM-APP-0913), `docs/corpus/SYNTHESIS_*.md` (SOM-DOC-0910/0911/0912)

---

## 0. Where we actually are (one paragraph)

The protocol is true and audited: 128-bit GYST UUIDv8, bit-exact, RFC 9562, three hostile
self-audits survived (rand42, content-address seeding, ms/sec ts). The engine is real: 52.77M
Polymarket trades minted with zero dupes, native bitmask routing proven in Postgres, 1.49M ops/s
in-process decode, live gated status site. The research is real: 19 Kalshi edge studies from our
own 30GB corpus. What has NEVER happened: a real dollar moving through the system. Every
money-claim in the corpus was either design-only (Locus/Vertex/x402) or debunked by our own
reality checks (Hormuz). The single highest-leverage move is a small, verified, UUID-native
real-money P&L — it converts the whole corpus from research into a track record.

---

## 1. PHASE 0 — CONSOLIDATE (Days 1–2)  «one spec, one encoder, one registry»

The corpus's residual defects are all *fragmentation* defects. Kill them:

- **P0.1 — Encoder unification.** `src/common/gyst.py` low-word packing diverges from the
  audited spec (`582fdee4`: `prov<<58 | sig<<42 | hash42`; gyst.py: `sig<<44 | prov<<40 | hash40`).
  Decide the canonical order (recommend: the audited gist spec), fix gyst.py +
  `uuid_service_turboquant.py` + any TS mirror, add a cross-language round-trip test.
  NOTE: the 52.77M rows were minted with the current gyst.py packing — either declare that
  packing canonical-v3 (cheaper) or version it via a spec flag. DECISION REQUIRED — flagged
  as the one schema-direction stop per standing rules.
- **P0.2 — Type registry unification.** Kalshi block collision: 0x3A4 (kalshi_uuid_bot) vs
  0x3A5/0x3A6 (codebook.ts) vs 0x3B0–0x3B2 (gyst_master.py). Write `docs/SOM-SPEC-TYPES.md`
  as the single source; add trading lifecycle types: 0x3A7 FILL, 0x3A8 POSITION_SNAPSHOT,
  0x3A9 SETTLEMENT, 0x3AA PNL_MARK.
- **P0.3 — Freeze protocol v3.0.0.** Tag the repo; the spec doc + test harness + registry
  become the defendable artifact.
- **P0.4 — Ghost Catalog sweep.** Every new artifact carries the header (done for all Phase-0+
  outputs); backfill any missing headers in scripts/.

Verification: cross-language round-trip test green; `proof_transaction.py` re-run green.

## 2. PHASE 1 — UUID-NATIVE TRADING LEDGER (Days 2–4)

Build on local PG next to `uuid_trades` (spawn model per `pipe_a_to_b.py`):

- Tables: `uuid_orders`, `uuid_fills`, `uuid_positions` (rollup view), `uuid_pnl`.
  All keyed `uuid_hi/uuid_lo BIGINT` + `parent_uuid_hi/lo` edges.
- **Reconciliation-by-construction:** Kalshi `client_order_id` = the order UUID's deterministic
  42-bit tail (already implemented in `kalshi_uuid_bot.py`). Exchange ACK → UUID with no
  lookup table.
- Fill poller (`GetFills`), settlement poller, mark-to-market job.
- P&L = SQL walk of the spawn tree: SUM(settlement.signal×qty − fill_px×qty − fees) grouped
  by type bitmask + market namespace.
- Extend the truth loop: a P&L number is PROVEN only when it reconciles against exchange
  API output. Nightly `proof_transaction.py` over the ledger.

Deliverable: dry-run order → simulated fill → P&L row, end-to-end, all UUIDs.

## 3. PHASE 2 — PAPER GATE (Weeks 1–3)  «reinstate the abandoned discipline»

The Vercel-era system had the right gate (60+ resolved @ >55%) and never reached it. Reinstate:

- Strategies, evidence-ranked from our own 19 studies:
  1. **Maker/passive capture** — maker premium + NO-side bias proven in 52M rows.
  2. **Calibration/longshot** — win_rate_by_price + mispricing_by_price buckets.
  3. **Cross-venue divergence** Poly↔Kalshi — v_twin_signal_pairs pattern; minutes-scale.
  4. **Event-driven** (BTC 5-min oracle lag) — seconds-scale, last to enable.
- Gates: disposition ≥ 0.70 (edge 35/conf 30/trend 20/book 10/sent 5); consensus gate
  (model direction AND book imbalance agree — 57%→71% historical uplift).
- Live Kalshi WS feed → mint 0x3A1 quotes → in-proc bitmask filter → strategy → paper 0x3A4.
- **Latency honesty:** this is fast event-driven (100ms–s), NOT HFT. No colo, rate-limited
  REST. Wirespeed maths wins in-process (pre-filtering streams), not in queue position.

Exit gate to Phase 3: 60+ resolved paper positions >55%, OR maker net-of-fee capture
positive over 2+ consecutive weeks. No exceptions.

## 4. PHASE 3 — GO-LIVE (explicit GO required from Phoenix)

- Obtain `KALSHI_KEY_ID` + `KALSHI_PRIVATE_KEY` (RSA-PSS). Wire into `kalshi_uuid_bot.py`.
- Hard limits day one: $1–5/contract, 5 contracts/market max, daily-loss kill switch,
  per-domain exposure caps. Kill switch = one env flag checked before every submit.
- Every order/fill/settlement/mark is a UUID in the ledger. Publish a P&L pane on
  uuid.somacosf.com (passkey-gated first; public when you choose).
- Kalshi first (regulated US venue). Polymarket leg (Polygon wallet + py-clob-client) only
  after Kalshi P&L reconciles for 2+ weeks — it adds the cross-venue book.

## 5. PHASE 4 — EXPAND (post-P&L)

- **Says convergence:** city posts minted on the same substrate; a topic namespace spans
  Polymarket + Kalshi + city posts + X. Sentiment roll-up from spawn generations
  (`/api/rollup?master=<uuid>`), the reason the 24-bit ts exists.
- **sgw.somacosf.com** aggregate landing; per-city posting portals (visitor content → UUID).
- **GeoHex exact addressing:** invertible planar-hex refinement (gyst-hex-substrate skill)
  so hex↔UUID is bijective — the "effective GPS" claim becomes literal.
- **Agent-money layer:** with a real track record, Locus/Vertex/x402 move from design to
  integration; the trading ledger already IS the contract-settlement pattern they need.

---

## 6. Standing rules honored throughout

.bk before overwrites · archive-don't-delete · no Vercel deploy without GO · gists secret ·
Ghost Catalog headers · uv not pip · truth-loop: no claim without a command that ran.

## 7. Immediate next actions (my queue on your word)

1. P0.1 packing decision — I present both options with migration cost, you pick. (STOP point)
2. P0.2 SOM-SPEC-TYPES.md — mechanical, I proceed.
3. Phase 1 ledger schema + fill poller — mechanical after P0 decisions, I proceed and commit stages.
4. You: open a Kalshi account / generate API keys when Phase 2 gate is in sight.
