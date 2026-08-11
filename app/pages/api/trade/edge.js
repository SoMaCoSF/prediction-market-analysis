// file_id: SOM-TS-1000-v1.0.0 name: api/trade/edge.js description: Edge finder — compares model probabilities to live Kalshi market prices to find where betting makes more project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, edge, kalshi, mlb, arb, probability] created: 2026-08-11 version: 1.0.0 agent_id: HERMES-AGENT
// API: /api/trade/edge — fetches live Kalshi MLB game markets, compares to model probabilities, returns sorted edge list
const HOST = process.env.KALSHI_HOST || "https://api.elections.kalshi.com/trade-api/v2";

// Default model picks (can be overridden via POST body or query param)
const DEFAULT_PICKS = [
  { game: "Cleveland vs Detroit", pick: "Detroit", probability: 0.55, team_code: "DET", match_code: "CLEDET" },
  { game: "Chicago C vs Washington", pick: "Chicago C", probability: 0.62, team_code: "CHC", match_code: "CHCWSH" },
  { game: "Seattle vs New York Y", pick: "New York Y", probability: 0.55, team_code: "NYY", match_code: "SEANYY" },
  { game: "New York M vs Atlanta", pick: "Atlanta", probability: 0.56, team_code: "ATL", match_code: "NYMATL" },
  { game: "Philadelphia vs St. Louis", pick: "Philadelphia", probability: 0.62, team_code: "PHI", match_code: "PHISTL" },
  { game: "Colorado vs Arizona", pick: "Arizona", probability: 0.63, team_code: "AZ", match_code: "COLAZ" },
  { game: "Milwaukee vs San Diego", pick: "Milwaukee", probability: 0.54, team_code: "MIL", match_code: "MILSD" },
  { game: "Tampa Bay vs A's", pick: "Tampa Bay", probability: 0.63, team_code: "TB", match_code: "TBATH" },
  { game: "Kansas City vs Los Angeles D", pick: "Los Angeles D", probability: 0.65, team_code: "LAD", match_code: "KCLAD" },
];

async function fetchMarketDetail(ticker) {
  try {
    const r = await fetch(`${HOST}/markets/${ticker}`, {
      headers: { "Accept-Encoding": "identity" },
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) return null;
    const data = await r.json();
    return data.market || data;
  } catch {
    return null;
  }
}

async function fetchMLBGames() {
  const r = await fetch(`${HOST}/markets?limit=200&status=open&series_ticker=KXMLBGAME`, {
    headers: { "Accept-Encoding": "identity" },
    signal: AbortSignal.timeout(10000),
  });
  if (!r.ok) return [];
  const data = await r.json();
  return data.markets || [];
}

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");

  // Allow overriding picks via POST
  let picks = DEFAULT_PICKS;
  if (req.method === "POST" && req.body && req.body.picks) {
    picks = req.body.picks;
  } else if (req.query.picks) {
    try { picks = JSON.parse(req.query.picks); } catch { /* use defaults */ }
  }

  const out = { edges: [], ts: Math.round(Date.now() / 1000), source: "kalshi" };
  try {
    const markets = await fetchMLBGames();
    const edges = [];

    for (const pick of picks) {
      // Find the matching market — look for the team code in the ticker
      // Markets come in pairs (one per team). We want the one ending in our team's code.
      const candidates = markets.filter((m) => {
        const t = m.ticker || "";
        return t.includes(pick.match_code) && t.endsWith("-" + pick.team_code);
      });

      // Pick the nearest (soonest closing) game
      candidates.sort((a, b) => (a.close_time || "").localeCompare(b.close_time || ""));

      for (const mkt of candidates.slice(0, 1)) {
        const detail = await fetchMarketDetail(mkt.ticker);
        if (!detail) continue;

        const yesAsk = Number(detail.yes_ask_dollars ?? detail.yes_ask ?? 0);
        const yesBid = Number(detail.yes_bid_dollars ?? detail.yes_bid ?? 0);

        if (yesAsk <= 0 || yesAsk > 0.99) continue;

        // The edge: model probability vs market price
        // If we BUY YES at the ask, our expected value = (prob * $1) - ask_price
        const evPerContract = pick.probability * 1.0 - yesAsk;
        const edgePct = evPerContract * 100;
        const roi = yesAsk > 0 ? (evPerContract / yesAsk) * 100 : 0;

        // Also compute NO side: if we think team wins at P, opponent wins at 1-P
        const noProb = 1 - pick.probability;
        const noAsk = 1 - yesBid; // NO ask = 1 - yes_bid (approximately)
        const noEdge = noProb - noAsk;

        edges.push({
          game: pick.game,
          pick: pick.pick,
          team_code: pick.team_code,
          model_prob: Math.round(pick.probability * 100),
          market_yes_ask: Math.round(yesAsk * 100),
          market_yes_bid: Math.round(yesBid * 100),
          market_no_ask: Math.round(noAsk * 100),
          edge_yes_cents: Math.round(edgePct),
          edge_no_cents: Math.round(noEdge * 100),
          ev_per_contract_cents: Math.round(evPerContract * 100),
          roi_pct: Math.round(roi),
          best_side: edgePct >= noEdge ? "YES" : "NO",
          best_edge_cents: Math.round(Math.max(edgePct, noEdge) * 100),
          ticker: mkt.ticker,
          close_time: mkt.close_time,
          kalshi_url: `https://kalshi.com/markets/${mkt.ticker}`,
        });
      }
    }

    // Sort by best edge descending
    edges.sort((a, b) => b.best_edge_cents - a.best_edge_cents);
    out.edges = edges;
    out.summary = {
      total_games: edges.length,
      positive_edges: edges.filter((e) => e.best_edge_cents > 0).length,
      best_edge: edges[0] || null,
    };
  } catch (e) {
    out.error = String(e).slice(0, 200);
  }
  res.status(200).json(out);
}
