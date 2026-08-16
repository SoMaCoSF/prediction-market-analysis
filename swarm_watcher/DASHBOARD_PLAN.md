# Dashboard Plan — Up/Down Signal Swarm Corpus

> No deploy yet. This defines WHAT to present and the data contract
> (`corpus_view.build_corpus_view`) the UI consumes.

## What makes this corpus incredible (presentation priorities)
1. **The swarm tension graph** — a single live bar: market bias 0–1, with
   each wallet plotted as a dot along it. W_UP far right (green), W_DOWN far
   left (red). The *spread* between the extremes IS the story ("down-swarm vs
   up-response").
2. **Wallet cards sorted by `|divergence_vs_market|`** — the most interesting
   wallets first. Each card shows: GYST `0x3F0` + `0x3F2` UUIDs, bias gauge,
   contrarian meter, stickiness sparkline, polarity label.
3. **Pattern badges** — STRONG_UP / STRONG_DOWN / CONTRARIAN / MOMENTUM, derived
   from (bias, stickiness) so the user instantly sees *behavior*, not just ratio.
4. **Swarm event feed** — `swarm_events` (FLIP / CONVERGE / DIVERGE / SWARM_UP /
   SWARM_DOWN) as a timeline. This is the "who is moving when" layer.
5. **UUID provenance strip** — every wallet + signal is a substrate UUIDv8; a
   click expands the 128-bit breakdown (type 0x3F0/0x3F2, namespace, signal).
   Ties the corpus into the whole SoMaCoSF GYST cloud.

## Data contract (already implemented)
`build_corpus_view(store)` →
```
{
  market_bias, market_polarity, total_wallets, up_swarm[], down_swarm[],
  wallets[ {wallet, gyst_wallet, gyst_signal, n_actions, up, down, bias,
             bias_weighted, market_bias, contrarian, stickiness,
             divergence_vs_market, polarity} ],
  events[ {t, kind, wallet, detail} ]
}
```

## Rendering options (decision deferred until user approves public surface)
- **A) Local-only**: a `python -m swarm_watcher.serve` tiny HTTP server
  (`http.server`) returning the JSON + a single HTML file. Zero Vercel. Fastest,
  private, matches "keep it local."
- **B) Next.js route** under somacosf-platform (`/swarm`) — only after the user
  says GO and we add it to the Vercel allow-list. Reuses existing LCARS theme.

## Current status
- Math: 31/31 tests pass.
- Corpus builder: working on synthetic + live-optional ingest.
- Dashboard: contract done; UI not built (awaiting GO to present publicly).
