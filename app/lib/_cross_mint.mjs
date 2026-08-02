// cross-verify driver: mint with the JS port using identical fixed inputs
import { mintMarketUuid, mintOrder, mintAck, hiLo, lo42 } from "./trade-uuid.mjs";

const TS = 1_800_000_000;
const mkt = mintMarketUuid("KXMLB-26-LAD", TS);
const order = mintOrder({ ticker: "KXMLB-26-LAD", side: "yes", priceCents: 41, count: 1, parentUuid: mkt, ts: TS });
const ack = mintAck({ orderUuid: order.uuid, exchangeOrderId: "a410c673-6cad-4747-96d0-f8ac5fca5145", avgFillPriceCents: 40.9, tsMs: 1_800_000_060_000 });
console.log(JSON.stringify({
  market: mkt,
  order_uuid: order.uuid,
  order_hi: order.hi,
  order_lo: order.lo,
  client_order_id: order.clientOrderId,
  ack_uuid: ack.uuid,
  ack_hi: ack.hi,
  ack_lo: ack.lo,
}));
