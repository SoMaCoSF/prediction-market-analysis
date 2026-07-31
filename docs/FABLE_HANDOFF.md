<!-- =============================================================================== file_id: SOM-DOC-0907-v1.0.0 name: FABLE_HANDOFF.md description: Handoff brief for Fable (next-tier model) — how to run and take the GYST UUID engine + entire *.says.com network to the next level project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [handoff, fable, says-com, strategy, next-level] created: 2026-07-30 modified: 2026-07-30 version: 1.0.0 agent_id: HERMES-AGENT =============================================================================== -->

# FABLE HANDOFF — Take This to the Next Level

**Audience:** Fable (the larger model that runs after this session).
**Author:** Hermes Agent (this session), on behalf of Phoenix / SoMaCoSF.
**Scope:** the GYST UUIDv8 prediction-market engine AND the entire `*.says.com` network we own.

---

## 0. TL;DR for Fable
You inherit a working **UUID-native data engine** (not a foreign-key DB). The UUID is the
primitive: every entity — a market, a price tick, a city post, a vendor — is a 128-bit GYST
UUIDv8 carrying type / namespace / timestamp / fractal / signal / provenance in its bits.
Roll-up and routing are **O(1) bitmask queries**, not joins. Your job: extend this from
"prediction-market trades" to the **whole says.com intelligence network** and make the
cross-system signal graph real.

---

## 1. What is built and PROVEN (do not rebuild — extend)
| artifact | status | proof |
|---|---|---|
| 30 GB Polymarket corpus → GYST UUIDv8 | DONE | 52.77M trade rows minted, 0 uuid-dupes |
| Native 128-bit bitmask routing (Postgres) | DONE | `(uuid_hi>>52)&4095 = type` indexes; impossible on Turso/SQLite (64-bit) |
| Per-transaction proof harness | DONE | `proof_transaction.py`: 3000/3000 real rows, 0 failures, 100% bitmask |
| Local source-of-truth Postgres (OMEN-01) | DONE | 52.77M rows, portable PG 16.4, MAC-gated |
| Supabase rolling subset (cloud, <500MB) | DONE | `uuid_trades_subset` = 1.5M freshest rows, chunked COPY sync |
| Vercel status site `uuid.somacosf.com` | DONE + LIVE | passkey-gated (SHA-256 of OMEN-01 MAC), reads Supabase |
| Private GH repo | DONE | `SoMaCoSF/prediction-market-analysis` (secrets never committed) |
| Ghost Catalog convention | DONE | every artifact carries `file_id` header (docs/GHOST_CATALOG.md) |
| DR recovery point | DONE | `D:/somacosf/backups/manual/uuid_trades_DR_2026-07-30.dump` (2.2GB, validated) |

**Dupe reality (important):** `total=52,770,500`, `distinct_uuid=52,770,500` (0 uuid dupes),
`distinct_trade_id=21,004,654`. The 31.7M shared `trade_id`s are LEGITIMATE — a trade_id is
not unique across the corpus; the UUID is. **Do not "dedup" — the UUID is the key.**

---

## 2. The architecture Fable must honor
- **Master event → child spawn hierarchy (NxN).** Master UUID (0x3A0) is root. Every price
  tick / state change = a child UUID (0x3A1 quote / 0x3A2 trade) with `fractal_depth=1`,
  `fractal_domain` = parent's, `fractal_generation++`, `namespace=fnv1a12(parent_uuid)`.
  Updates are NEVER in-place — a change spawns a new child. History *emerges* by roll-up.
- **24-bit timestamp is intentional** (real-time sentiment channel). Do NOT widen it.
- **Roll-up = bitmask query**, not join. This is the wirespeed payoff.
- **Constraint:** GYST `namespace` is only 12 bits (4096) — fast-filter only. Exact roll-up
  needs an explicit `parent_uuid` column. The current `uuid_trades` is flat (joined by string
  `market_id`) — it predates the spawn model. **Retrofit `parent_uuid` + a `uuid_quotes`
  (0x3A1) table** when you next backfill from `data/data.tar.zst` (immutable source).
- **Vision:** UUIDize any concept across any system/language into a shareable, mineable signal.
  128 bits always fit the foreign context.

---

## 3. The entire *.says.com network we own
Phoenix owns the `*.says.com` city intelligence network + sibling properties. Fable should
treat ALL of these as UUID-addressable nodes on the same GYST substrate:

| property | role | state | next-level move |
|---|---|---|---|
| **citysays.vercel.app** | hub of the network | private GH `SoMaCoSF/citysays`, Next.js 15 + R3F + TursoDB | make every "city says" post a GYST UUID; cross-link to markets |
| **newyork / miami / sanfrancisco / austin / chicago / losangeles .says.com** | city nodes | harvest MVP at aiventix.vercel.app | per-city posting portal (visitor submits text+topic+place → minted UUID) |
| **somacosf.com** (+ `uuid.somacosf.com` now live) | protocol/engine surface | this engine | the UUID control plane for the network |
| **popsoc.vercel.app** | social event templates (6 templates) | frozen at v0.1.0-full | events minted as GYST UUIDs; sentiment roll-up |
| **sgw.somacosf.com** (planned) | central landing for ALL says.coms | not built | aggregate global + per-city UUID feeds, tenant switcher |

**Reference infra to port (do not reinvent):** `D:/outputs/austinsays-platform`
(`app/pulse/kiosk` portal pattern + `UUID_engine/gyst_uuid.ts` encoder) and
`D:/somacosf/outputs/somacosf-platform` (`app/uuid` 8-tab LCARS harness).

**Known crash to avoid:** R3F v8 + Next 15 → `ReactCurrentOwner` undefined. Fix = React 19 + R3F v9.

---

## 4. What Fable should BUILD next (prioritized)
1. **Spawn retrofits.** Add `parent_uuid` + `uuid_quotes` (0x3A1) to the engine; re-backfill
   from `data.tar.zst`. Prove roll-up: "all children of master X" via bitmask + parent edge.
2. **Sentiment from UUID graph.** Price-quote generations → sentiment signal per master.
   This is the reason for the short ts + spawn model. Ship `/api/rollup?master=<uuid>`.
3. **Cross-system linking.** Mint city posts (citysays) and markets (this engine) on the SAME
   substrate; a "topic" becomes a namespace that spans Polymarket + X tweets + city posts.
4. **Tailscale↔Vercel full-local connect (Phase 2).** Optional: relay OMEN-01 → Vercel so the
   full 52M is live, not just the 1.5M Supabase subset. Needs a relay host + auth.
5. **Per-city posting portals** on each `*.says.com` node (visitor-submitted content → UUID).
6. **sgw.somacosf.com** aggregate landing.

---

## 5. Operational facts Fable needs
- **Local PG:** `D:/somacosf/outputs/prediction-market-analysis/.pg/pg16/pgsql`, user `postgres`,
  pw `hermes_pg_2026` (in `.env_turso`, NOT in git). Start: `scripts/start_pg.bat`.
- **Supabase:** project `somacosf-uuid-engine`, ref `qxxuovjqdknxxzrnlpow`, org `SomacoSF`.
  Sync: `scripts/sync_supabase_subset.py` (chunked COPY, 50k/statement — free-tier timeout).
- **Vercel:** project `app` (team somacosfs-projects), domain `uuid.somacosf.com`, env
  `PG_CONNECTION_STRING` (Supabase) + `STATUS_SALT` (passkey salt). Redeploy: `vercel deploy --prod`.
- **Secrets:** NEVER commit `.env_turso` / `.pg/`. Ghost Catalog headers on every artifact.
- **Phoenix rules (NON-NEGOTIABLE):** .bk before any overwrite; archive-don't-delete; never
  deploy Vercel without explicit GO; match screenshots exactly; keyboard 's' key drops — treat
  missing 's' as typo. GitHub private by default. Gists secret by default.

---

## 6. The one-liner for Fable
> "You have a UUID-native engine that proves trades are addressable, routable, and rollable in
> 128 bits. Now make the entire says.com network addressable the same way, and let sentiment
> emerge from the spawn graph. The substrate is built. Extend it — don't rebuild it."
