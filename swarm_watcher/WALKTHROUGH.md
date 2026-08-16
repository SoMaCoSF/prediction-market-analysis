# Swarm Math — Walkthroughs

Three worked examples that walk the math from raw ticks to a classified,
UUID-bearing corpus entry. All numbers are reproducible via
`python -m swarm_watcher.demo` and the unit tests in `tests_math.py`.

---

## Walkthrough 1 — A single UP wallet

**Input ticks** (wallet `W_UP`): 18 UP (+1), 2 DOWN (−1).

```
up, down = 18, 2
bias        = 18 / 20            = 0.900   → STRONG_UP
bias_weighted (if sizes equal) = 0.900
market_bias (this wallet alone vs itself) → n/a in isolation
stickiness  = mean(acf(lag 1..5)) ≈ −0.01  → ~random timing, directional mass is just "up"
```

**Read:** W_UP is a net upward swarm. Its GYST `0x3F2` signal UUID carries
`signal = round(0.900 × 65535) = 58981` in bits 42–57 of the low word. A
dashboard can re-derive "this wallet is 90% up" directly from the UUID.

---

## Walkthrough 2 — Divergence: up-swarm vs down-swarm

Two wallets in the SAME window:
- `W_UP`:  bias 0.900
- `W_DOWN`: bias 0.100

```
swarm_divergence(W_UP, W_DOWN) = 0.900 − 0.100 = +0.800
```

**Read:** +0.800 means W_UP is pushing the market UP *relative to* W_DOWN, which
is pushing it DOWN. This is the "down-signal swarm vs up-signal response" the
user described — now quantified. A dashboard sorts wallets by
`|divergence_vs_market|` and paints W_UP green, W_DOWN red, the gap between them
as the active tension.

---

## Walkthrough 3 — Stickiness reveals the CONTRARIAN

`W_CONTRA` alternates: 5 UP, 5 DOWN, 5 UP, 5 DOWN (blocky). Counts are 10/10 →
`bias = 0.500` (looks NEUTRAL by ratio alone). But:

```
signed flow buckets: [+5, −5, +5, −5]
autocorrelation lag-1 ≈ −0.6   → stickiness ≈ −0.5
```

**Read:** the *ratio* hides the pattern. The *stickiness* exposes it: W_CONTRA
is **mean-reverting / contrarian** — it commits to a direction then flips.
`contrarian_score` vs a neutral market is ~0 (it's 50/50 overall) but its
temporal signature is the opposite of a "sticky" directional swarm. This is why
we compute BOTH bias AND stickiness — ratio alone misclassifies this wallet.

---

## Why two layers (ratio + temporal)

| Wallet | bias | stickiness | classification |
|--------|------|------------|---------------|
| W_UP   | 0.90 | ~0.0       | STRONG_UP, momentum |
| W_DOWN | 0.10 | ~0.0       | STRONG_DOWN, momentum (dump) |
| W_CONTRA | 0.50 | −0.5      | NEUTRAL ratio, CONTRARIAN behavior |

The corpus is "incredible" precisely because it separates *what direction a
wallet nets* (bias) from *how it behaves over time* (stickiness/contrarian).
Neither alone is enough; together they fingerprint the wallet.

## GYST provenance
- Wallet identity: `0x3F0 TRADER_WALLET`, provenance `WALLET(6)`.
- Derived signal: `0x3F2 TRADER_SIGNAL`, provenance `SWARM(7)`, signal = bias.
- Both validate as UUIDv8 (`uuid.UUID(s).version == 8`) and decode back to
  their type code — so the corpus is queryable by type across the whole
  substrate, not just inside this module.
