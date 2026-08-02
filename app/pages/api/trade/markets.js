// file_id: SOM-TS-0928-v1.0.0 name: api/trade/markets.js description: Live Kalshi markets proxy (public, dollar/fixed-point schema) project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, markets, kalshi, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
const HOST = process.env.KALSHI_HOST || "https://api.elections.kalshi.com/trade-api/v2";

const cents = (v) => {
  if (v == null) return null;
  const f = Number(v);
  if (Number.isNaN(f)) return null;
  return f <= 1 ? Math.round(f * 100) : Math.round(f);
};

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  const series = req.query.series;
  try {
    const params = new URLSearchParams({ limit: "200", status: "open" });
    if (series) params.set("series_ticker", series);
    const r = await fetch(`${HOST}/markets?${params}`, { headers: { "Accept-Encoding": "identity" } });
    const d = await r.json();
    const rows = (d.markets || []).map((m) => ({
      ticker: m.ticker,
      title: (m.title || m.subtitle || "").slice(0, 80),
      yes_bid: cents(m.yes_bid_dollars ?? m.yes_bid),
      yes_ask: cents(m.yes_ask_dollars ?? m.yes_ask),
      ask_size: Number(m.yes_ask_size_fp || 0),
      volume: Number(m.volume_fp || m.volume || 0),
      close_time: m.close_time,
    }));
    rows.sort((a, b) => b.volume - a.volume);
    res.status(200).json({ markets: rows.slice(0, 25) });
  } catch (e) {
    res.status(502).json({ error: String(e).slice(0, 200) });
  }
}
