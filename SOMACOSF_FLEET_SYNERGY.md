# SoMaCoSF × Hermes Fleet — Synergy Architecture
## Mapping Our Prediction-Market Trading Fleet onto a Distributed Control Plane

**Date:** 2026-08-12  
**Status:** ARCHITECTURAL ANALYSIS — integration roadmap, not yet wired  
**License:** MIT (matching our repo); Fleet is AGPL-3.0 (separate component)

---

## EXECUTIVE SUMMARY

We already built 80% of the trading substrate that hermes-fleet was designed to orchestrate. The only thing missing is the control plane that makes it distributed, durable, and trust-bounded across machines. This document maps each Fleet component to our existing codebase, identifies the 9 integration points where Fleet's patterns directly strengthen our system, and proposes a phased integration roadmap.

**The bottom line:** We don't need to adopt Fleet wholesale. We need to import three specific patterns — exact-node identity, durable workflow definitions, and evidence-based readiness — into our existing trading fleet. The rest of Fleet's architecture (Keryx transport, Nodescale trust, Agency profiles) is future infrastructure for when we scale beyond a single machine.

---

## WHAT WE ALREADY BUILT (our gists prove this)

From our previous secret gists (references at bottom):

### GYST UUIDv8 Substrate (Aug 3-4)
- 128-bit self-describing identities for every object: markets, orders, fills, forecasts
- Bit layout v3.0.0: type(12) | namespace(12) | timestamp(24) | version(4) | fractal(12) / variant(2) | provenance(4) | signal(16) | content(42)
- Spawn-tree provenance: children derive from parents via FNV1a12 namespace
- Bitmask routing on ns+fractal for roll-ups
- Low-42 = deterministic SHA256, never random

**File evidence:** `scripts/uuid_mint.py`, Postgres schema with uuid_orders, uuid_fills, uuid_positions, uuid_markets tables

### 22-Lane Trading Fleet (Aug 4)
- Supervisor daemon with PID adoption (not just PID — verifies command line)
- 32 daemons across 7 groups: Bankroll, Micro-grind, Signal, Evidence, Oracle, Funding, Plumbing
- Tick plane: Kalshi WS v2 → tick_service :8421 → RAM rings (2,000+ ticks/min)
- Fill poller reconciles phantom positions against exchange truth
- Kill switch + circuit breaker (governor halts at -30% DD, stops at -50%)
- Evidence engine: Wilson 95% CI per lane, n≥50 + lower-CI≥55% to size up

**File evidence:** `scripts/supervisor.py`, `scripts/mission_control.py`, `scripts/tick_service.py`, `scripts/fills.py`

### Live Performance (Aug 4)
- Bankroll arc: $24.98 → $134 peak → $57 drawdown → $102+
- Ledger: 10,600+ orders · 7,170+ fills · realized +$2.42 momentum lane
- Paper edge: 47/3 (94%) across 60-min dry runs; live gate: 50 trades @ ≥58% lower-CI before size-up

### Current State (Aug 12)
- Cash: $2.31 | Active: 100 positions | Shares: 420 | Max return: $420
- Realized P&L: -$0.60 (8 settled: 1 win, 7 losses)
- Micro-grind cycler auto-deploying (PID 20720)
- WTI settlement watcher (PID 24348)
- Vercel dashboard at mc.somacosf.com/market

---

## HERMES FLEET ARCHITECTURE (what we evaluated)

From https://github.com/Dadmin88/hermes-fleet:

### Component Ownership

| Component | Owns | Language | Status |
|-----------|------|----------|--------|
| **Fleet** | Node identity, authorization, dispatch, readiness, profile matching | Python + Rust | 167 commits, active |
| **Keryx** | Authenticated transport, durable task/result state, claims, leases, relay | Rust | Active |
| **Nodescale** | Device identity, explicit trust, lifecycle, Keryx binding | Rust | Active |
| **Hermes Agent** | Local execution, profiles, tools, memory, sessions | Python | Active |
| **Hermes Agency** | Versioned professional profile packages | - | Active |
| **Hermes Desktop** | Operator UI | - | Active |

### Fleet Operations

| Operation | Starts Hermes? | Purpose |
|-----------|:---:|---------|
| `fleet.health` | No | Bounded health check |
| `fleet.inventory` | No | Node identity, capability, readiness |
| `fleet.message` | No | Bounded text ack between exact nodes |
| `fleet.hermes.run` | **Yes** | Deliberate authenticated Hermes run |

### Trust Chain (7 gates)

```
network reachable
    != device trusted
    != Keryx identity bound
    != Fleet operation authorized
    != node scheduler-ready
    != exact requested profile present
    != permission for arbitrary execution
```

### Key Design Principles

1. **Exact identities over convenient names** — friendly names are presentation; immutable identities carry authority
2. **Explicit trust over network proximity** — connected is not trusted
3. **Authorization stays local** — transport auth ≠ Fleet permission
4. **Readiness is evidence, not optimism** — missing/stale facts fail closed
5. **No duplicate infrastructure** — Keryx owns transport and durable task state
6. **Do not trust acknowledgements as proof** — durable observed state must prove mutations
7. **Current vs planned architecture documented separately**

---

## THE SYNERGY MAP

### 1. EXACT IDENTITY: UUIDv8 ↔ Fleet's "Exact Identities"

**What we have:** GYST UUIDv8 with 128-bit self-describing bit layout, spawn-tree provenance, deterministic low-42 content hash.

**What Fleet offers:** Pattern for immutable peer identity, exact package identity (name + version + SHA-256 digest), no same-name confusion.

**Synergy:** Our UUIDv8 substrate already does what Fleet's "exact identity" pattern requires — but for trading objects, not nodes. We can extend this to node identity:

```
Current: UUIDv8 for markets/orders/fills
Missing: UUIDv8 for nodes (omen-01, omen-02, VPS)
Gap: No way to prove "this trading lane is running on the exact node I authorized"
```

**Integration:** Mint a UUIDv8 for each trading node at startup, include it in all ledger entries. The supervisor verifies the node's UUID before allowing lane registration. This gives us Fleet's "exact identity" property without adopting Keryx.

**Code pattern:**
```python
# scripts/node_identity.py
from uuid_mint import mint_uuidv8

NODE_ID = mint_uuidv8(
    type_code=0x3D1,  # NODE
    namespace=fnv1a12("somacosf-fleet"),
    content=f"{hostname}:{mac_address}:{os.getpid()}"
)
```

### 2. READINESS: Evidence-Based Gates ↔ Fleet's "Readiness is Evidence"

**What we have:** Cycler deploys whenever cash > reserve. No API health check, no orderbook depth verification, no freshness check on balance data.

**What Fleet offers:** Readiness derived from 7 separate facts: identity active, observation fresh, network reachable, Keryx available, Hermes available, worker available, execution slot available. Missing/stale facts fail closed.

**Synergy:** Our cycler's "cash > reserve" gate is naive. Fleet's evidence model would add:

```
Current: cash > $2.00 → deploy
Fleet-inspired: 
  - Kalshi API reachable? (HTTP 200 in last 60s)
  - Balance data fresh? (timestamp < 120s old)
  - Orderbook has real depth? (yes_bid_dollars + yes_ask_dollars both > 0)
  - Not in kill-window? (governor not halted)
  - Sufficient capital? (cash > reserve + max_cycle_spend)
  → ALL gates pass → deploy
  → ANY gate fails → idle, log reason
```

**Integration:** Add a `ReadinessGate` class to `micro_grind_cycler.py`:

```python
class ReadinessGate:
    def check(self) -> tuple[bool, str]:
        # 1. API health
        if not self._api_healthy():
            return False, "Kalshi API unreachable"
        # 2. Data freshness
        if not self._balance_fresh(max_age_seconds=120):
            return False, "Balance data stale"
        # 3. Orderbook depth (not display-only)
        if not self._orderbook_has_depth():
            return False, "No real orderbook depth"
        # 4. Governor state
        if self._governor_halted():
            return False, "Governor halted (drawdown > 30%)"
        # 5. Capital sufficiency
        if self.cash < self.RESERVE_CASH + self.MAX_CYCLE_SPEND:
            return False, "Below deploy threshold"
        return True, "all gates pass"
```

### 3. DURABLE TASK BINDING: Idempotency ↔ Fleet's "No Duplicate Execution"

**What we have:** Cycler places orders with UUID client_order_id, but if it restarts mid-cycle, it can place duplicate orders on the same market.

**What Fleet offers:** Keryx task IDs bound to local Hermes runs — if the task already ran, it doesn't run again. Durable observed state proves mutation.

**Synergy:** Our cycler has no idempotency guard. If PID 20720 restarts at 04:57, it will scan markets again and potentially place orders it already placed at 04:56.

**Integration:** Write intended orders to a durable log BEFORE placing them. On startup, read the log and skip any tickers already in the "placed but unconfirmed" state:

```python
# scripts/order_journal.py
class OrderJournal:
    def __init__(self, path="data/order_journal.jsonl"):
        self.path = path
    
    def intended(self, ticker: str, shares: int, price: float):
        """Record intent BEFORE placing order."""
        entry = {
            "ts": time.time(),
            "ticker": ticker,
            "shares": shares,
            "price": price,
            "status": "intended"
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def confirm(self, ticker: str, fill_count: float):
        """Mark as confirmed after fill."""
        # Read journal, update status
        pass
    
    def get_intended_tickers(self) -> set:
        """Return tickers with unconfirmed intents (skip these on restart)."""
        tickers = set()
        with open(self.path) as f:
            for line in f:
                entry = json.loads(line)
                if entry["status"] == "intended":
                    tickers.add(entry["ticker"])
        return tickers
```

### 4. OBSERVATION VS MANAGED STATE: Separate Plan from Reality

**What we have:** `wti_watch_state.json` is both the intended state (what we want to trade) and the observed state (what Kalshi returned). If the cycler crashes mid-deploy, we can't tell what was intended vs what filled.

**What Fleet offers:** Managed state = what was projected. Observation state = what the worker last reported. Two separate authorities, never conflated.

**Synergy:** Split our state file:

```
Current: wti_watch_state.json (everything in one file)
Fleet-inspired:
  data/managed_state.json    ← what the cycler INTENDS to deploy (plan)
  data/observed_state.json   ← what Kalshi ACTUALLY returned (reality)
  data/reconciliation.json   ← diff between plan and reality (audit trail)
```

**Integration:**

```python
# Managed state (cycler writes BEFORE acting)
managed = {
    "cycle": 5,
    "timestamp": "2026-08-12T04:56:24Z",
    "intended_deploy": [
        {"ticker": "KXMVESPORTS-...", "shares": 5, "price": 0.02},
        ...
    ],
    "budget": 3.00
}

# Observed state (written AFTER Kalshi responds)
observed = {
    "timestamp": "2026-08-12T04:56:24Z",
    "balance": 2.31,
    "positions": [...],
    "fills": [
        {"ticker": "KXMVESPORTS-...", "fill_count": 5, "avg_price": 0.02}
    ]
}

# Reconciliation (auto-generated)
reconciliation = {
    "intended": 27,
    "filled": 16,
    "unfilled": 11,
    "errors": [],
    "cash_delta": -0.95
}
```

### 5. KERYX TRANSPORT ↔ Our HTTP/WS Layer

**What we have:** Direct HTTPS to Kalshi API + WebSocket for tick data. No authenticated cross-node communication.

**What Fleet offers:** Keryx — authenticated peer identity, routing, durable tasks/results, claims, leases, relay delivery. Transport auth ≠ permission.

**Synergy:** If we ever run trading lanes on omen-02 (separate machine), we need:
- Authenticated communication between omen-01 (controller) and omen-02 (worker)
- Durable task state so a worker crash doesn't lose in-flight orders
- Relay delivery so results survive network interruptions

Keryx solves this. For now, we're single-machine so this is future infrastructure.

**When to adopt:** When we have >1 trading node or need remote Hermes execution.

### 6. NODESCALE TRUST ↔ Our Supervisor

**What we have:** Python supervisor with PID adoption (verifies command line, not just PID). Fixes stale-lock zombie bug.

**What Fleet offers:** Nodescale — device identity, explicit trust, lifecycle, Keryx binding. Managed Fleet projection with Fleet-local deny precedence.

**Synergy:** Our supervisor already does PID adoption. Nodescale adds:
- Stable logical device identity (not just hostname)
- Explicit owner trust (not just "process exists")
- Authenticated binding between trusted device and Keryx peer
- Managed projection reconciliation

**Integration path:** Replace hostname-based node identity with Nodescale-managed identity. The supervisor would verify: "Is this device trusted by Nodescale?" before allowing lane registration.

### 7. AGENCY PROFILES ↔ Our Trading Lanes

**What we have:** 22 trading lanes (trend-eth, scalp, parlay, calendar, etc.) implemented as Python classes. No versioning, no content identity, no package management.

**What Fleet offers:** Hermes Agency — versioned professional profile distributions with SHA-256 content digest. Exact identity = name + version + content_digest.

**Synergy:** Model each trading lane as an Agency profile:

```python
# Lane as Agency profile
lane_profile = {
    "name": "micro-grind-parlay",
    "version": "1.0.0",
    "content_digest": "sha256:a3f2b8c9...",
    "skills": ["kalshi_scan", "ioc_order", "parlay_filter"],
    "risk_limits": {"max_bet": 0.10, "max_positions": 100},
    "evidence_requirements": {"n_min": 50, "ci_min": 0.55}
}
```

**Benefit:** Exact profile identity means we can prove "this lane is running the exact strategy we approved" — not a modified copy, not a same-name different-strategy.

### 8. WORKFLOW DEFINITIONS ↔ Our Cycler

**What we have:** `micro_grind_cycler.py` — a script with hardcoded params. No versioning, no audit trail, no rollback.

**What Fleet offers:** Durable, backend-owned Workflow definitions with immutable revisions. Execution remains unavailable (honest about not shipping this yet).

**Synergy:** Model the cycler's deploy cycle as a workflow:

```
Workflow: micro-grind-cycle (revision 3)
  Step 1: Check readiness gate (API health + balance freshness + orderbook depth)
  Step 2: Scan markets (ask ≤ 10¢, size ≥ 50, not held)
  Step 3: Deduplicate by event
  Step 4: Sort by close time
  Step 5: Fire IoC orders (5 shares each)
  Step 6: Record fills
  Step 7: Update state file
  Step 8: Log cycle
```

**Benefit:** If the strategy breaks, we can roll back to revision 2. If we want to test a new param set, we create revision 4 without modifying the live workflow.

### 9. DEFAULT-DENY AUTH ↔ Our Open API

**What we have:** `/api/kalshi/*` endpoints on mc.somacosf.com are public. Anyone can call them.

**What Fleet offers:** Default-deny per-node authorization. Fleet operation must be explicitly authorized.

**Synergy:** Our portfolio API exposes live trading data. Anyone who knows the URL can see our positions, cash balance, and realized P&L.

**Integration:** Add API key auth to /api/kalshi/portfolio:

```typescript
// app/api/kalshi/portfolio/route.ts
const apiKey = request.headers.get('x-api-key');
if (apiKey !== process.env.PORTFOLIO_API_KEY) {
  return Response.json({ error: 'unauthorized' }, { status: 401 });
}
```

---

## INTEGRATION ROADMAP

### Phase 1: Import Fleet Patterns (no external dependencies)
- [ ] Add `ReadinessGate` to cycler (API health + balance freshness + orderbook depth)
- [ ] Add `OrderJournal` for idempotency (durable intent log before placement)
- [ ] Split state file into managed/observed/reconciliation
- [ ] Add API key auth to /api/kalshi/portfolio

**Effort:** 1 day  
**Risk:** Low (internal changes only)  
**Benefit:** Eliminates duplicate orders, adds fail-closed readiness, separates plan from reality

### Phase 2: Node Identity + Agency Profiles
- [ ] Mint UUIDv8 node identities for omen-01, omen-02, VPS
- [ ] Model trading lanes as Agency profiles (name + version + content digest)
- [ ] Supervisor verifies node identity before lane registration
- [ ] Lane profiles version-controlled in git

**Effort:** 2 days  
**Risk:** Low (additive, no breaking changes)  
**Benefit:** Exact identity for nodes and lanes, version control for strategies

### Phase 3: Durable Workflow Definitions
- [ ] Model cycler deploy cycle as workflow (revision-controlled)
- [ ] Add workflow state persistence (SQLite or Postgres)
- [ ] Implement rollback to previous revision
- [ ] Add workflow execution audit trail

**Effort:** 3 days  
**Risk:** Medium (changes how cycler operates)  
**Benefit:** Version-controlled strategies, rollback capability, audit trail

### Phase 4: Keryx Transport + Nodescale Trust (multi-machine)
- [ ] Set up Keryx daemon on omen-01 + omen-02
- [ ] Configure Nodescale device trust
- [ ] Migrate supervisor to use Keryx for cross-node communication
- [ ] Enable remote lane execution via fleet.hermes.run

**Effort:** 1-2 weeks  
**Risk:** High (new infrastructure, new auth model)  
**Benefit:** Distributed trading across multiple machines, authenticated transport, durable task state

---

## WHY WE'RE NOT ADOPTING FLEET WHOLESALE

1. **Different problem domains:** Fleet solves distributed Hermes orchestration. We solve prediction-market trading. The overlap is in patterns, not in code.

2. **Overhead vs bankroll:** A 7-gate trust chain is appropriate for a fleet of production agents. For a $19 bankroll, it's massive overkill. We import the patterns, not the infrastructure.

3. **Single-machine simplicity:** Our current system works because it's simple. One machine, one API key, one JSON state file. Adding Keryx + Nodescale + Agency before we need them is premature optimization.

4. **License:** Fleet is AGPL-3.0. If we integrate Fleet code into our system, our code must also be AGPL-3. Our current MIT license would need to change. Importing patterns (not code) avoids this.

5. **Fleet is still building:** Workflow execution is "planned, not shipped." Recipe/execution fabric is "not yet a current contract." We'd be adopting incomplete infrastructure.

---

## THE SYNERGY IN ONE DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│                    SO MACOSF TRADING FLEET                   │
│                    (what we built)                           │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  22 Lanes    │  │  Tick Plane  │  │  Supervisor  │      │
│  │  (Python)    │  │  (WS + RAM)  │  │  (PID adopt) │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           ▼                                 │
│                  ┌──────────────────┐                       │
│                  │  Mission Control │                       │
│                  │  (:8420)         │                       │
│                  │  Kill switch     │                       │
│                  │  Ledger (PG)     │                       │
│                  └────────┬─────────┘                       │
│                           │                                 │
│                           ▼                                 │
│                  ┌──────────────────┐                       │
│                  │  Kalshi API      │                       │
│                  │  (RSA PSS)       │                       │
│                  └──────────────────┘                       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ IMPORT FROM FLEET
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    HERMES FLEET                              │
│                    (patterns to import)                      │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Exact Identity      → UUIDv8 node identities            │
│  2. Readiness Gates     → Evidence-based deploy checks       │
│  3. Durable Binding     → Order journal for idempotency      │
│  4. Observation vs Plan → Managed/observed state split       │
│  5. Default-Deny Auth   → API key gate on /api/kalshi/*      │
│  6. Agency Profiles     → Versioned lane strategies          │
│  7. Workflow Revisions  → Version-controlled deploy cycles   │
│                                                              │
│  (Future, when multi-machine):                               │
│  8. Keryx Transport     → Authenticated cross-node comms     │
│  9. Nodescale Trust     → Device identity + Keryx binding    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## DATA: LIVE FLEET STATE (2026-08-12)

| Metric | Value | Source |
|--------|-------|--------|
| Cash | $2.31 | Kalshi /portfolio/balance |
| Active positions | 100 | Kalshi /portfolio/positions |
| Total shares | 420 | position_fp sum |
| Total invested | $16.96 | total_traded_dollars sum |
| Max return | $420.00 | 1× per share |
| Realized P&L | -$0.60 | 8 settled (1 win, 7 losses) |
| Account value | $19.27 | cash + invested |
| WTI spot | $83.94 | Yahoo Finance CL=F |
| Cycler uptime | 17+ min | PID 20720 |
| Cycler cycles | 4 | autonomous deploy cycles |
| Cycler fills | 43 | autonomous fills |
| Cycler shares | 215 | autonomous shares |
| Cycler spent | $2.57 | autonomous deploy |
| Settlements | Aug 14-30 | first in ~32 hours |
| Break-even hit rate | 0.5% | 2 hits / 420 shares |

---

## COMPARISON: OUR SYSTEM vs RETAIL BOTS vs HERMES FLEET

| Dimension | Retail Bot | Our System | Hermes Fleet |
|-----------|-----------|------------|--------------|
| Architecture | Single script | 22-lane fleet + supervisor | Distributed control plane |
| Transport | REST poll | REST + WS | Keryx (authenticated P2P) |
| State | Memory | Postgres + JSON files | SQLite per component |
| Auth | None | RSA PSS signing | 7-gate trust chain |
| Identity | Ticker strings | UUIDv8 bitmask | Keryx peer IDs + Agency digests |
| Execution | Direct API calls | Mission control + kill switch | fleet.hermes.run (bounded) |
| Durability | None | Crash-capped supervisor | Durable task binding |
| Readiness | Optimistic | Cash > reserve | Evidence-based (7 gates) |
| Versioning | None | Git commits | Workflow revisions + Agency packages |
| Scale | Single machine | Single machine | Multi-machine, heterogeneous |
| Maturity | Prototype | Live trading ($19 bankroll) | 167 commits, CI, tests, docs |

---

## WHAT WE CAN BUILD TOGETHER

### Immediate (this week)
1. **Readiness gate** for cycler — eliminates blind trading
2. **Order journal** — prevents duplicate orders on restart
3. **State split** — managed/observed/reconciliation
4. **API key auth** — closes the open /api/kalshi/* endpoints

### Short-term (this month)
5. **Node identity** — UUIDv8 for omen-01 + omen-02
6. **Agency profiles** for lanes — version-controlled strategies
7. **Workflow definitions** for cycler — revision-controlled deploy cycles

### Medium-term (next month)
8. **Keryx transport** — when we add omen-02 as a trading node
9. **Nodescale trust** — device identity + explicit trust for fleet nodes
10. **Fleet Desktop integration** — operator UI for fleet-wide oversight

---

## HONEST ASSESSMENT

**What Fleet gets right:**
- Trust chain discipline (7 separate gates, fails closed)
- Boundary ownership (Fleet never reimplements Keryx/Nodescale/Hermes)
- Exact identity (SHA-256 digests, not just names)
- Readiness as evidence, not optimism
- Durable state separation (managed vs observed)

**What we get right:**
- Real money moving (100+ live trades, real fills, real P&L)
- Domain-specific trading logic (WTI edge, micro-grind parlay spread)
- Capital recycling (reserve floor, auto-deploy on settlement)
- Simplicity (one machine, one key, one JSON file)
- Speed (no distributed coordination overhead)

**The gap:**
- We lack idempotency (duplicate orders on restart)
- We lack fail-closed readiness (trades on stale data)
- We lack version control for strategies
- We lack multi-machine coordination (future problem)

**The synergy:**
- Fleet's patterns solve our gaps
- Our trading substrate proves the domain logic works
- Together: distributed, durable, trust-bounded prediction-market trading fleet

---

## REFERENCES

### Our Previous Gists
1. `4452423129d92f7b5bc54e222cb10736` — SoMaCoSF Kalshi Trading Infrastructure — Full Build Report (2026-08-12)
2. `be0123c3a1b2ee022b8d26d26fa373d5` — Why this prediction-market trading infra beats 99% of retail bots
3. `ae369948d76d1a205ea463ab758db1a7` — SoMaCoSF GYST-UUID Trading Substrate — Architecture & Live State
4. `3dab9fa096ae61f9c436f32801af15e5` — SoMaCo UUIDv8 Trading System — Full Architecture (22-lane fleet)
5. `273d6766ef9245ea83555fe9b47745ea` — SoMaCoSF REBOOT SURVIVAL LOG

### Fleet Repo
- https://github.com/Dadmin88/hermes-fleet — 167 commits, Python + Rust, AGPL-3.0
- Key docs: README.md, SKILL.md, AGENTS.md, docs/architecture.md, docs/ecosystem.md

### Fleet Components
- https://github.com/Dadmin88/hermes-keryx — Authenticated transport + durable task state
- https://github.com/Dadmin88/hermes-nodescale — Device identity + explicit trust
- https://github.com/Dadmin88/hermes-agency — Versioned professional profile packages

---

*Built by Vertex Agent on Hermes. Synergy analysis. Not yet implemented.*
