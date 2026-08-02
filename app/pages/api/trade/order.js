// file_id: SOM-TS-0930-v1.0.0 name: api/trade/order.js description: Order endpoint — passkey-gated PAPER/LIVE fire with caps, kill switch, UUID mint, ACK child, ledger writes project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [api, order, fire, trade, kalshi] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
import { q } from "../../../lib/trade-db";
import { passkeyOk, isKilled, logEvent } from "../../../lib/trade-mc";
import { createOrderV2, keysPresent } from "../../../lib/trade-kalshi";
import { mintOrder, mintAck } from "../../../lib/trade-uuid";

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({ error: "POST only" });
  const b = req.body || {};
  if (!passkeyOk(b.passkey)) {
    await logEvent("warn", "order REJECTED: bad passkey");
    return res.status(403).json({ error: "bad passkey" });
  }
  const ticker = String(b.ticker || "").trim();
  const side = String(b.side || "").toLowerCase();
  const price = Number(b.price);
  const count = Number(b.count);
  const mode = String(b.mode || "paper").toLowerCase();
  if (!ticker || !["yes", "no"].includes(side) || !(price >= 1 && price <= 99) || !(count >= 1 && count <= 5) || !["paper", "live"].includes(mode)) {
    return res.status(400).json({ error: "invalid ticker/side/price/count/mode (count<=5)" });
  }
  if (price * count > 500) return res.status(400).json({ error: `cap: notional ${price * count}c > 500c ($5)` });

  const o = mintOrder({ ticker, side, priceCents: price, count });
  try {
    if (mode === "paper") {
      await q(
        `INSERT INTO uuid_orders (uuid, uuid_hi, uuid_lo, client_order_id, parent_uuid, ticker, side, price_cents, count, status, mode, ts)
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'filled','paper',$10) ON CONFLICT (uuid) DO NOTHING`,
        [o.uuid, o.hi, o.lo, o.clientOrderId, o.parentUuid, ticker, side, price, count, o.ts]);
      await logEvent("paper", `PAPER fill ${side} ${price}c x${count} ${ticker} uuid=${o.uuid.slice(0, 13)}… coi=${o.clientOrderId}`);
      return res.status(200).json({ ok: true, mode: "paper", uuid: o.uuid, client_order_id: o.clientOrderId });
    }

    // ---- live ----
    if (await isKilled()) {
      await logEvent("kill", "LIVE order BLOCKED by kill switch");
      return res.status(423).json({ error: "kill switch engaged" });
    }
    if (b.confirm !== "FIRE") return res.status(400).json({ error: "live requires confirm=FIRE" });
    if (!keysPresent()) return res.status(400).json({ error: "KALSHI keys not configured" });

    await q(
      `INSERT INTO uuid_orders (uuid, uuid_hi, uuid_lo, client_order_id, parent_uuid, ticker, side, price_cents, count, status, mode, ts)
       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'submitting','live',$10) ON CONFLICT (uuid) DO NOTHING`,
      [o.uuid, o.hi, o.lo, o.clientOrderId, o.parentUuid, ticker, side, price, count, o.ts]);
    await logEvent("live", `LIVE submit ${side} ${price}c x${count} ${ticker} uuid=${o.uuid.slice(0, 13)}… coi=${o.clientOrderId}`);

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
      } catch (e) { await logEvent("warn", `ack mint warn: ${String(e).slice(0, 120)}`); }
      await q("UPDATE uuid_orders SET status='submitted', exchange_order_id=$1 WHERE uuid=$2", [oid, o.uuid]);
      await logEvent("live", `LIVE ACK order_id=${oid} fill_count=${json.fill_count} coi=${o.clientOrderId} (reconciles by low-42 bitmask)`);
      return res.status(200).json({ ok: true, mode: "live", uuid: o.uuid, client_order_id: o.clientOrderId, exchange_order_id: oid, ack: json });
    }
    await q("UPDATE uuid_orders SET status='rejected' WHERE uuid=$1", [o.uuid]);
    await logEvent("error", `LIVE REJECTED ${status}: ${JSON.stringify(json).slice(0, 200)}`);
    return res.status(400).json({ error: "exchange rejected", status, resp: json });
  } catch (e) {
    await logEvent("error", `order exception: ${String(e).slice(0, 160)}`);
    return res.status(500).json({ error: String(e).slice(0, 200) });
  }
}
