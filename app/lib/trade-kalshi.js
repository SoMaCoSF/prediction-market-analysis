// file_id: SOM-TS-0923-v1.0.0 name: lib/trade-kalshi.js description: Kalshi V2 REST signing + order placement (RSA-PSS) for the trade mission control project_id: PREDICTION-MARKET-ANALYSIS category: app tags: [kalshi, signing, v2, orders, trade] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
/** lib/trade-kalshi.js — Kalshi V2 REST (RSA-PSS request signing).
 *  Mirrors the verified Python path: sign "{ts_ms}{METHOD}{/trade-api/v2/path}"
 *  with RSA-PSS/SHA-256. Env: KALSHI_KEY_ID + (KALSHI_PRIVATE_KEY | KALSHI_PRIVATE_KEY_PATH).
 *  Never logs key material.
 */
import crypto from "crypto";
import fs from "fs";

const HOST = process.env.KALSHI_HOST || "https://api.elections.kalshi.com/trade-api/v2";

function privateKey() {
  if (process.env.KALSHI_PRIVATE_KEY) return process.env.KALSHI_PRIVATE_KEY;
  if (process.env.KALSHI_PRIVATE_KEY_PATH) return fs.readFileSync(process.env.KALSHI_PRIVATE_KEY_PATH, "utf8");
  throw new Error("KALSHI_PRIVATE_KEY / KALSHI_PRIVATE_KEY_PATH not set");
}

export function keysPresent() {
  return Boolean(process.env.KALSHI_KEY_ID && (process.env.KALSHI_PRIVATE_KEY || process.env.KALSHI_PRIVATE_KEY_PATH));
}

function sign(method, path, tsMs) {
  const signer = crypto.createSign("RSA-SHA256");
  signer.update(`${tsMs}${method.toUpperCase()}${path}`);
  return signer.sign({ key: privateKey(), padding: crypto.constants.RSA_PKCS1_PSS_PADDING, saltLength: 32 }, "base64");
}

async function call(method, apiPath, body) {
  const ts = String(Date.now());
  const fullPath = `/trade-api/v2${apiPath}`;
  const headers = {
    "KALSHI-ACCESS-KEY": process.env.KALSHI_KEY_ID,
    "KALSHI-ACCESS-SIGNATURE": sign(method, fullPath, ts),
    "KALSHI-ACCESS-TIMESTAMP": ts,
    "Content-Type": "application/json",
  };
  const res = await fetch(`${HOST}${apiPath}`, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json().catch(() => ({ raw: "non-json response" }));
  return { status: res.status, json };
}

/** Create Order V2: YES contract book. Buy YES at P¢ = bid @ P/100.
 *  Buy NO at P¢ = ask @ (100-P)/100 (mirror!). */
export async function createOrderV2({ ticker, side, priceCents, count, clientOrderId }) {
  const v2Side = side === "yes" ? "bid" : "ask";
  const v2Price = side === "yes" ? priceCents / 100 : (100 - priceCents) / 100;
  return call("POST", "/portfolio/events/orders", {
    ticker,
    client_order_id: clientOrderId,
    side: v2Side,
    count: `${Number(count).toFixed(2)}`,
    price: v2Price.toFixed(4),
    time_in_force: "good_till_canceled",
    self_trade_prevention_type: "taker_at_cross",
    post_only: false,
    cancel_order_on_pause: false,
    reduce_only: false,
    subaccount: 0,
    exchange_index: -1,
  });
}

/** Signed GET helper — returns parsed json (used by read-only planes like TIME markets). */
export async function kalshiFetch(apiPath) {
  const { json } = await call("GET", apiPath);
  return json;
}

export async function getFills(params = {}) {
  const qs = new URLSearchParams(params).toString();
  return call("GET", `/portfolio/fills${qs ? "?" + qs : ""}`);
}

export async function getOrder(orderId) {
  return call("GET", `/portfolio/orders/${orderId}`);
}
