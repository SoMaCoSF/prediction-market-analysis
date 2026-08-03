// file_id: SOM-TS-0955-v1.0.0 name: api/trade/tim_order.js description: Tim's order route — PIN-gated (TIM_PIN env), hard caps ($2/order, $20/day), ledger-minted via the same V2 path project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, tim, order, guest, caps] created: 2026-08-03 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";
import { isKilled, logEvent } from "../../../lib/trade-mc";
import { createOrderV2, keysPresent } from "../../../lib/trade-kalshi";
import { mintOrder, mintAck } from "../../../lib/trade-uuid";

const MAX_ORDER_C = 200;        // $2 per bet
const DAILY_CAP_C = 2000;       // $20 per day
const MAX_COUNT = 4;

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  const b = req.body || {};
  if (!process.env.TIM_PIN || String(b.pin) !== process.env.TIM_PIN) {
    return res.status(403).json({ error: "wrong PIN" });
  }
  const ticker = String(b.ticker || "").trim();
  const side = String(b.side || "").toLowerCase();
  const price = Number(b.price);
  const count = Number(b.count);
  if (!ticker || !["yes", "no"].includes(side) || !(price >= 1 && price <= 99) || !(count >= 1 && count <= MAX_COUNT)) {
    return res.status(400).json({ error: "invalid bet (count<=4)" });
  }
  const notional = price * count;
  if (notional > MAX_ORDER_C) return res.status(400).json({ error: `cap: $${MAX_ORDER_C / 100} per bet` });
  if (await isKilled()) return res.status(423).json({ error: "kill switch engaged" });
  if (!keysPresent()) return res.status(400).json({ error: "keys not configured" });

  const day = new Date().toISOString().slice(0, 10);
  const key = `tim:spent:${day}`;
  let spent = 0;
  try {
    const rows = await q("SELECT v FROM mc_state WHERE k=$1", [key]);
    spent = rows.length ? Number(rows[0].v) : 0;
  } catch { /* first day */ }
  if (spent + notional > DAILY_CAP_C) {
    return res.status(400).json({ error: `daily cap: $${DAILY_CAP_C / 100} (spent $${(spent / 100).toFixed(2)})` });
  }

  const o = mintOrder({ ticker, side, priceCents: price, count, parentUuid: b.parentUuid || null });
  try {
    await q(
      `INSERT INTO uuid_orders (uuid, uuid_hi, uuid_lo, client_order_id, parent_uuid, ticker, side, price_cents, count, status, mode, ts)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'submitting','live',$10) ON CONFLICT (uuid) DO NOTHING`,
      [o.uuid, o.hi, o.lo, o.clientOrderId, o.parentUuid, ticker, side, price, count, o.ts]);
    const { status, json } = await createOrderV2({ ticker, side, priceCents: price, count, clientOrderId: o.clientOrderId });
    if (status === 200 || status === 201) {
      const oid = json.order_id || (json.order || {}).order_id || null;
      const avgPxC = json.average_fill_price != null ? Number(json.average_fill_price) * 100 : null;
      try {
        const ack = mintAck({ orderUuid: o.uuid, exchangeOrderId: String(oid), avgFillPriceCents: avgPxC, tsMs: json.ts_ms });
        await q(
          `INSERT INTO uuid_acks (uuid, uuid_hi, uuid_lo, parent_uuid, exchange_order_id, fill_count, remaining_count, avg_price_cents, ts)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) ON CONFLICT (uuid) DO NOTHING`,
          [ack.uuid, ack.hi, ack.lo, ack.parentUuid, String(oid), Number(json.fill_count || 0), Number(json.remaining_count || 0), avgPxC, ack.ts]);
      } catch { /* ack optional */ }
      await q("UPDATE uuid_orders SET status='submitted', exchange_order_id=$1 WHERE uuid=$2", [oid, o.uuid]);
      await q(
        "INSERT INTO mc_state (k, v, updated_at) VALUES ($1, $2, now()) ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v, updated_at=now()",
        [key, String(spent + notional)]);
      await logEvent("tim", `TIM bet ${side} ${price}c x${count} ${ticker} fill=${json.fill_count}`);
      return res.status(200).json({ ok: true, exchange_order_id: oid, fill_count: json.fill_count, avg: avgPxC });
    }
    await q("UPDATE uuid_orders SET status='rejected' WHERE uuid=$1", [o.uuid]);
    return res.status(400).json({ error: "exchange rejected", resp: json });
  } catch (e) {
    return res.status(500).json({ error: String(e).slice(0, 200) });
  }
}
