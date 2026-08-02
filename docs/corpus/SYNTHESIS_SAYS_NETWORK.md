<!-- =============================================================================== file_id: SOM-DOC-0911-v1.0.0 name: SYNTHESIS_SAYS_NETWORK.md description: Says network & platform corpus synthesis — 11+ domains, Locus/Vertex/SPOCTALK agent layer, verticals, built-vs-design ledger project_id: PREDICTION-MARKET-ANALYSIS category: doc tags: [corpus, synthesis, gists, uuid, gyst] created: 2026-07-31 modified: 2026-07-31 version: 1.0.0 agent_id: FABLE-HERMES =============================================================================== -->

# SAYS NETWORK / SoMaCoSF PLATFORM — Corpus Synthesis
*Source: local gist archives (C:/Users/Phoenix/somaco_gists_2026, 102 objects) + D:/somacosf/somacosf_corpus.csv (396 rows). Gist IDs cited as 8-char prefixes. Note: the SGW gists (`198841e8`, `4c5907ab`, `cd1ba2e6`) and WireStripper gists (`9e264f42`, `b03c3bf0`) are **not present in the local archive**; SGW/citysays appear nowhere in the archived corpus — WireStripper coverage below comes from secondary references (`3c4a8975`, `77f6b87d`, corpus CSV).*

---

## 1. The *.says.com Network

The Says Network is a constellation of city-branded domains, each a **SPOC** (Single Point of Contact) node running the same Next.js template with city-specific content, deployed under the SoMaCo Vercel team (`team_MJNSdIKAxPJySa21R8pNNlXZ`) (`8457b7bc`). The March 2026 state reports (`d4bb816b`, `77f6b87d`) are the corpus's own ground-truth audits and are ruthless about what's real:

**LIVE (production, auto-deploy on push):**
- **austinsays.com** — the primary node; full kiosk + admin, GYST UUID generator lives inside this repo (1,383 files) (`d4bb816b`, `5b07a398`).
- **sonomasays.com** — wine-country variant, second production deploy (712 files).

**PARTIAL:** **newyorksays.com** — "CLI-only": repo doesn't exist on GitHub; deployed only via Vercel CLI (56 files) (`77f6b87d`).

**REGISTERED / TEMPLATE-ONLY (domain owned, SPOC UUID allocated, no deploy):** miamisays.com, napasays.com, and the wine portfolio — californias.vin, frances.vin, marthas.vin, wineries.vin (each a 27-file template clone with no git, no node_modules) (`d4bb816b`).

**PLANNED (proposal-level only):** chicagosays.com, lasays.com, sanfranciscosays.com, londonsays.com, parissays.com, tokyosays.com (`8457b7bc` lists them with team rosters; no repos exist). The narrative gist `fd0a7892` claims a "deployed 11-city network"; the PRD (`77f6b87d`) corrects this: *"one live city node… federation is documented, not deployed."*

**Adjacent surfaces:** `says-hub` repo ("City Intelligence Nodes + UUID v8 city visualization", corpus CSV SOM-REP-0033); `spoc-admin` (admin panel for all nodes, built); `hexsays` hex-grid layer; **popsoc.vercel.app** as the multi-vertical host (below); **somacosf.com** as the markets/signal platform (Hormuz, /poly, /showcase). Domain economics: 9 "Says" domains acquired for ~$150–200 total (`d4bb816b`). **citysays and sgw.somacosf.com: no evidence in local corpus.**

---

## 2. Federated Payment / Agent Layer — **almost entirely DESIGN-ONLY**

The PRD's own verdict (`77f6b87d`): *"Zero Locus API integration code exists… $0 revenue… 0 agent contracts executed."*

**Locus escrow** (`e683cb8b`, `2bfcccd3`): Locus (paywithlocus.com, YC F25) is an external AI-agent payment platform on Base L2 — ERC-4337 smart wallets, gasless USDC, email escrow with TTL, x402 pay-per-call APIs, a Fiverr-style human-task marketplace, subwallets (≤100/wallet), policy guardrails. The gists map GYST type block **0x400–0x40A** onto it (WALLET 0x400, ESCROW 0x403, X402_CALL 0x404, FIVERR_ORDER 0x405, SETTLEMENT 0x409, DISBURSEMENT 0x40A) with deterministic seeds (`escrow:{email}:{amount}:{ts}`) giving idempotent retries and join-free lifecycle tracking. Real on-chain contract addresses are cited (router `0x3418…806`, USDC on Base). **Status: analysis/proposal — a pitch *to* Locus, not an integration.**

**Says Network payment mesh** (`8457b7bc`): one master SoMaCo wallet, one subwallet per city domain; `hashNamespace12(domain)` makes the domain portfolio literally the payment topology. Cross-city bets (Miami user, Yankees game, three namespaces, one escrow), parlays, wine-reservation escrows, canvas cards for every payment event on the Leaflet map. **Design-only.** Explicit in-corpus admission: "Missing: the actual money movement. BET_PICK exists as data, but there's no escrow, no USDC stake, no payout."

**Vertex LLC agent contracts** (`da946dd4`, `2250ec71`): AI agents registered as assets of a single California LLC (Vertex), each with deterministic UUID (type 0x501 AGENT_CITY_NODE, seed `agent:vertex.llc:AGENT-AUSTIN-001`); agent-to-agent contracts as type-0x510 UUIDs (idempotent from `contract:{A}:{B}:{terms_hash}`), 0x520-block LLC records, ESIGN/UETA (15 USC §7001) legal wrapper, genesis sequence of 5 bootstrap contracts, Locus escrow binding, sub-LLC spinning encoded in the depth nibble, and a registry at `registry.somacosf.com` with a full REST API. **Status per `77f6b87d`: "SPECIFIED + PARTIAL" — schema.sql and a SKILL.md exist (`2250ec71`), but the registry endpoint is not deployed and no contract has ever executed.** The visual gist's curl examples target a server that doesn't exist.

**SPOCTALK federation** (`45e7930e`, `3c4a8975`): recursive self-addressing — SPOC endpoints themselves carry UUIDs (0x1F0 endpoint / 0x1F1 aggregator), so "the infrastructure addresses itself." ~3,500 lines of production code, 25 files, 6 demo suites, all local proofs passing (witness dashboard port 4343, UUID API port 5000, discovery service with 9 registered endpoints), bandwidth analysis, dual-UUID (private/public HMAC-derived) security model. The 52KB evaluation (`3c4a8975`) reframes SPOCTALK as an **agent communication protocol** (UUID broadcast = self-selecting message bus; ~9 tokens per cross-network query) and concedes: *"the current federation is documented but not deployed as a running multi-endpoint network… The Says Empire endpoints exist as definitions."* registry.spoctalk.com: "Planned." **Verdict: BUILT AND TESTED single-node; multi-node federation never demonstrated live.**

**x402 / agent-to-agent commerce:** exists only as Locus's product surface plus GYST type 0x404 and roadmap items (#5 in the PRD critical path). One later mention that an "x402 payment gate" was wired on somacosf.com in year 2 (`edecd65d`), unverified elsewhere.

---

## 3. Platform Surfaces

**PopSoc** (repo `popsoc`, live at popsoc.vercel.app): "Popup Social Network for Events" — canvas-based Next.js 14 + Turso host platform and the corpus's real workhorse. **22 event templates** (wine_festival, tech_conference, farmers_market, wedding, golf_tournament…), 11+ verticals (events, congress, baseball cards, dining, wine, golf, mirage, ossuary) (`e2230f10`, `ec9a6b01`). **PopSoc Eats built & deployed**: /eats city selector, SF + NYC verticals (60 restaurants each), 5-page-per-city pattern, plus SonomaSays/NapaSays production hardening (`271c2574`). **PopSoc×PinDev "factory"** (spawn-a-PopSoc CLI, pin/discovery layer, 0x300 type block) is explicitly *"DESIGN PHASE — not yet implemented"* (`e2230f10`). **PopSoc×Locus** payments (5-UUID event spawn with wallet, vendor escrow, ticket sales) — design-only (`ec9a6b01`).

**Pulse / kiosk** (`5b07a398`, `9e78f3ce`): BUILT on austinsays.com — full-screen Leaflet map with floating, draggable canvas cards; UUID type badges decoded client-side; pulse venue/event schema; betting stream tab; admin API + uuid_registry SQLite; portal cards with `canvas_spec_json`. The betting *data* layer (0x2C0–0x2CC: markets, odds snapshots, picks, settlements) is live; money is not.

**Colloquy** (`c8ddbf8e`, `5e280135`, `b19dafd0`): UUID-native multi-turn sessions as first-class typed DAGs — colloquy 0x009 (depth 0) → agent_session 0x00A (depth 1) → turn 0x005 (depth 2), with semantic **heartbeats** (0x825, 11 registry-governed kinds, not timers). Storage split Turso (9 tables + rollup triggers) / Obsidian vault, neither solely authoritative. scheme_v=1 packs live telemetry into the 42 entropy bits so dashboards read cache performance from UUIDs alone. Cache economics: 6.35× savings via Anthropic 5-min prompt-cache warmth by construction. v0.0.2 adds agent birth certificates, witness chains (parent signs child's terminal claims), 3-axis spawn depth. Fifteen user stories answerable in one SQL round-trip each (prediction-market audit, FDA/SEC chain-of-custody) (`b19dafd0`). **Status: skill v0.1.0 frozen, schema shipped, scheme_v=0 shipped, "the system is running" — BUILT (local infrastructure, not a public product).**

**Signal service** (`10ae697b`, `99a8a2d6`): canonical markets-platform doc. Model: **concept** (attention target) → **sentiment_group** (typed actor cluster, 0x360–0x36F: whale.equity, farcaster.casts, news.publishers, reddit.subs, x.accounts, congress.stock-act, contracts.dod, sanctions.ofac) → **member** (influence-weighted) → **signal** (write-once Turso row). **Walletscape** = derived weighted graph per concept (`/api/walletscape?concept=X`, 60s cache). **Cardlet framework Phase A shipped 2026-04-22**: registry, SSE/WS/poll hooks, free-drag CardletHost, three wired cardlets (`coinbase.spot` ✅, `poly.analyze` ✅, `aero.pools` ✅). v0.2 addendum adds `markets.prediction.*` twin concepts, evidence.map forced-sequence cardlet, Leni Memo witness format, auto post-mortems (0x540 witness block), Vercel-cron trigger monitoring — **mostly plan, slotted into a 14-day sprint.** Every forecast on somacosf.com is bracketed by five live cardlets and committed as a witness UUID queryable via colloquy SQL.

**Mission control**: exists as a repo/gist thread (`9c02ae51`, `d04485b5` in digest) — CLAUDE.md-driven ops console; corpus treats it as tooling, not product.

**Ghost Catalog** (`3c4a8975`, `488d6a17`, `1aa21a34`): semantic file-identity system — every file carries a `SOM-XXX-NNNN-vX.Y.Z` header block (file_id, project, tags, agent_id); census verified 2026-02-15; duplicate detection, compliance watching, "phantom types" reveal declared-but-unbuilt capability. Packaged as a Factory Droid skill and used to build the 396-row corpus CSV itself. **BUILT and actively used** — it's the reason the archive is auditable.

---

## 4. DATA_WEAVING Meta-Layer (`d17af326`)

A single SQLite meta-database (`D:/somacosf/data_weaving.db`, 9 tables) that stores no application data — it maps the ecosystem: **55+ projects**, **12 active data domains** (Campaign Finance, Dossier, GYST Canvas, Golf, Baseball Cards, Oligarchology, CA Healthcare, Events, Auth, DMBT/Aegis, Wire Data, Universal Objects), **10 cross-domain "weave" relationships with strength scores** (e.g., Dossier→Campaign Finance shared_entity 0.95; Campaign Finance→Oligarchology cross_pollination 0.95), and **16 open data sources — 4 connected** (OSM, Unsplash, Congress.gov, embedded CA facilities JSON) **and 12 planned** (OpenFEC, SEC EDGAR, USASpending, CMS, ProPublica…). PopSoc is the host platform; the "mycelium" force-graph merges all domains. **BUILT** as a working local DB + PopSoc routes; the aspiration of a self-weaving fabric (`fb2c3c30`) is directional.

---

## 5. Intelligence Verticals

- **Hormuz Convergence Harvester** (`aea510b9` + reality-check `a1525d58`): Python loop cross-referencing Polymarket Gamma prices vs PredictParity GraphQL whale flow on Strait-of-Hormuz markets; registers itself as agent 0x504 (ENERGY domain), mints GYST v2 UUIDs per signal, ingests into somacosf.com Turso, whale tracking working ("trades=100 avg_yes=0.9961 whales=14"). **BUILT AND RUNNING — but the reality-check gist is brutal: no actual positions held; the Privy auth token was a domain-name string, not a JWT; both tracked markets already resolved; duplicate harvester processes dropped signals; Venmo funding failed everywhere.** Signal collection real, trading fictional.
- **AI Datacenter Supply Chain** (`ff33ad2c`): "$295B filed CapEx, zero Polymarket coverage" thesis; C-suite quote network from SEC 8-Ks, EDGAR scanner, Form-4 insider feed, Cu/Al busway substitution math, 0x3F0 signal types, live no-auth APIs and somacosf.com/showcase. **BUILT (harvesters + live routes), pre-revenue signal lattice.**
- **Oligarchology / Congress** (`8981afcd`): live at popsoc.vercel.app/congress — 100 senators, 20 tables, 52 PACs, 31 stock trades / 13 senators, family networks, suspicion scores, power ratings, 7 API endpoints, 6 pages, mycelium graph. **BUILT & DEPLOYED** (with the honest caveat of Vercel `/tmp` SQLite cold-start seeding).
- **Reckitt Brand Intelligence** (`dfdb2986`): 26 brands / 4 segments / 11 powerbrands / 24 cross-domain edges / ~130 SKUs, 0x1C0 enterprise type block, dark-intelligence UI, `buildReckittMapping()` in popsoc/lib. Gist says "Built 2026-02-12"; the PRD (`77f6b87d`) files it under **SPECIFIED/NOT BUILT** — treat as data-layer built inside PopSoc, enterprise product design-only.
- **MIRAGE** (`5188f0a3`): Gaza Reconstruction Intelligence Tracker — 24 entities, 9 money flows, 12 timeline events, 8 projects, "Board of Peace" network, plans-vs-reality ground-truth pages; 8 live routes at popsoc.vercel.app/mirage/*, 0x1D0 type block. **BUILT & DEPLOYED** (seed-data scale; type block "SPECIFIED" in PRD).
- **flightr** (`edecd65d`): geographic-substrate globe (Three.js + OpenSky ADS-B) bridging physical flows to prediction markets — an "honest assessment" gist rating the ecosystem (thesis 9/10, GYST 9/10) and prescribing 4 phases. **DESIGN-ONLY.**
- **WireStripper**: MCP tool-router choke point — intercepts tool calls, allow/deny/quarantine policy, unified SQLite + OTel logging; the enforcement layer of the agent stack (GYST=identity, SPOCTALK=federation, WireStripper=control) (`3c4a8975`). Repo `wire_stripper` exists (108 files, "Built" per `d4bb816b`), but PRD lists "WireStripper production deployment" under *what can wait* — **built prototype, not deployed.**

---

## Bottom Line (the corpus's own accounting, `77f6b87d`/`d4bb816b`)

Real: the GYST UUIDv8 protocol (58 types, 11 domains, 920+ entities), two live city nodes (Austin, Sonoma), PopSoc with 6+ deployed verticals, the cardlet/signal/colloquy observability stack, Ghost Catalog, DATA_WEAVING, and working harvesters. Design-only: every dollar-moving and multi-party claim — Locus payments, Vertex contracts, multi-node SPOCTALK federation, x402 revenue, the 9-city expansion. As the PRD concedes: *"one live city node, zero payment integration, zero agent-to-agent contract execution… The protocol itself is sound. The infrastructure around it needs building."*