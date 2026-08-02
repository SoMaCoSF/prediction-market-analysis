// file_id: SOM-TS-0924-v1.0.0 name: lib/trade-uuid.js description: Byte-exact JS port of the GYST UUIDv8 encoder (uuid_service_turboquant.py) + trading mints — identical UUIDs across Python/JS project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [uuid, gyst, encoder, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
/** lib/trade-uuid.js — GYST UUIDv8 encoder (JS, BigInt-exact).
 *  MUST match scripts/uuid_service_turboquant.py bit-for-bit. Cross-verified
 *  against the Python encoder before every deploy (scripts/_cross_mint.py).
 */
import crypto from "crypto";

const TYPE = { MARKET: 0x3b0, ORDER_BID: 0x3a4, ORDER_ASK: 0x3a5, ACK: 0x3a6, FILL: 0x3a7, SETTLE: 0x3a9, MARK: 0x3aa };
const PROV_KALSHI = 0x9;
const MASK42 = (1n << 42n) - 1n;
const TWO64 = 1n << 64n;
const TWO63 = 1n << 63n;

export function fnv1a12(label) {
  let h = 0x811c9dc5;
  for (const b of Buffer.from(label, "utf8")) {
    h ^= b;
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return (h ^ ((h >>> 12) & 0xfff)) & 0xfff;
}

function content42(...parts) {
  const seed = parts.map(String).join("|");
  const digest = crypto.createHash("sha256").update(seed, "utf8").digest();
  let v = 0n;
  for (let i = 0; i < 6; i++) v = (v << 8n) | BigInt(digest[i]);
  return v & MASK42;
}

export function encodeGyst({ typeCode, namespace, timestampSec, fractalDepth = 0, fractalDomain = 0, fractalGeneration = 0, signal = 0, provenance = 0, contentSeed = null }) {
  const ts = BigInt((timestampSec ?? Math.floor(Date.now() / 1000)) & 0xffffff);
  const fractal = BigInt(((fractalDepth & 0xf) << 8) | ((fractalDomain & 0xf) << 4) | (fractalGeneration & 0xf));
  const high = (BigInt(typeCode & 0xfff) << 52n) | (BigInt(namespace & 0xfff) << 40n) | (ts << 16n) | (8n << 12n) | fractal;
  const sigQ = BigInt(Math.max(0, Math.min(0xffff, Math.floor(Math.max(0, Math.min(1, signal)) * 0xffff))));  // truncate like Python int(), NOT round
  const prov = BigInt(provenance & 0xf);
  const parts = [typeCode & 0xfff, namespace & 0xfff, Number(ts), (fractalDepth & 0xf) << 8 | (fractalDomain & 0xf) << 4 | (fractalGeneration & 0xf), Number(sigQ), Number(prov)];
  if (contentSeed != null) parts.push(contentSeed);
  const r42 = content42(...parts);
  const low = (2n << 62n) | (prov << 58n) | (sigQ << 42n) | r42;
  const u128 = (high << 64n) | low;
  const hex = u128.toString(16).padStart(32, "0");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

const signed64 = (v) => (v >= TWO63 ? v - TWO64 : v);

export function hiLo(uuid) {
  const u = BigInt("0x" + uuid.replace(/-/g, ""));
  return { hi: signed64(u >> 64n).toString(), lo: signed64(u & (TWO64 - 1n)).toString() };
}

export function lo42(uuid) {
  return Number(BigInt("0x" + uuid.replace(/-/g, "")) & MASK42);
}

export function decodeGyst(uuid) {
  const u = BigInt("0x" + uuid.replace(/-/g, ""));
  const high = u >> 64n, low = u & (TWO64 - 1n);
  const sig = Number((low >> 42n) & 0xffffn);
  const fractal = Number(high & 0xfffn);
  return {
    typeCode: Number((high >> 52n) & 0xfffn),
    namespace: Number((high >> 40n) & 0xfffn),
    timestampSec: Number((high >> 16n) & 0xffffffn),
    fractalDepth: (fractal >> 8) & 0xf,
    fractalDomain: (fractal >> 4) & 0xf,
    fractalGeneration: fractal & 0xf,
    signalNormalized: sig / 0xffff,
  };
}

export function mintMarketUuid(ticker, ts = null) {
  return encodeGyst({
    typeCode: TYPE.MARKET, namespace: fnv1a12(`kalshi:${ticker}`), timestampSec: ts,
    fractalDepth: 0, fractalDomain: 0x1, signal: 1.0, provenance: PROV_KALSHI, contentSeed: ticker,
  });
}

export function mintOrder({ ticker, side, priceCents, count, parentUuid = null, ts = null }) {
  const tsSec = ts ?? Math.floor(Date.now() / 1000);
  const parent = parentUuid || mintMarketUuid(ticker, tsSec);
  const u = encodeGyst({
    typeCode: side === "yes" ? TYPE.ORDER_BID : TYPE.ORDER_ASK,
    namespace: fnv1a12(parent), timestampSec: tsSec,
    fractalDepth: 1, fractalDomain: 0x1, fractalGeneration: 1,
    signal: priceCents / 100, provenance: PROV_KALSHI,
    contentSeed: `order|${ticker}|${side}|${priceCents}|${count}|${tsSec}`,
  });
  return { uuid: u, ...hiLo(u), clientOrderId: lo42(u).toString(16), parentUuid: parent, ts: tsSec };
}

export function mintAck({ orderUuid, exchangeOrderId, avgFillPriceCents = null, tsMs = null }) {
  const d = decodeGyst(orderUuid);
  const tsSec = tsMs ? Math.floor(tsMs / 1000) : Math.floor(Date.now() / 1000);
  const u = encodeGyst({
    typeCode: TYPE.ACK, namespace: d.namespace, timestampSec: tsSec,
    fractalDepth: 2, fractalDomain: d.fractalDomain, fractalGeneration: d.fractalGeneration + 1,
    signal: avgFillPriceCents != null ? avgFillPriceCents / 100 : d.signalNormalized,
    provenance: PROV_KALSHI, contentSeed: `ack|${exchangeOrderId}`,
  });
  return { uuid: u, ...hiLo(u), parentUuid: orderUuid, ts: tsSec };
}

export function mintFill({ orderUuid, priceCents, exchangeFillId }) {
  const d = decodeGyst(orderUuid);
  const u = encodeGyst({
    typeCode: TYPE.FILL, namespace: d.namespace, timestampSec: Math.floor(Date.now() / 1000),
    fractalDepth: 2, fractalDomain: d.fractalDomain, fractalGeneration: d.fractalGeneration + 1,
    signal: priceCents / 100, provenance: PROV_KALSHI, contentSeed: `xf|${exchangeFillId}`,
  });
  return { uuid: u, ...hiLo(u), parentUuid: orderUuid };
}

export { TYPE, PROV_KALSHI };
