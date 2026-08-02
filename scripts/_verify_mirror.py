# verify the V2 side/price mapping WITHOUT firing real orders (capture outgoing body)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mission_control as mc

captured = {}

class FakeResp:
    status_code = 201
    headers = {"content-type": "application/json"}
    def json(self):
        return {"order_id": "fake", "fill_count": "0.00", "remaining_count": "1.00", "ts_ms": 1800000000000}

def fake_post(url, json=None, headers=None, timeout=None):
    captured["url"] = url
    captured["body"] = json
    captured["headers"] = {k: ("<redacted>" if "SIGNATURE" in k or "KEY" in k else v) for k, v in headers.items()}
    return FakeResp()

mc.httpx.post = fake_post
mc.kalshi_keys = lambda: ("fake-key-id", "fake-path")

def fake_sign(method, path, ts, kp):
    captured["signed_path"] = path
    return "fake-sig"
mc.kalshi_sign = fake_sign

# YES at 41c -> bid @ 0.4100
code, _ = mc.kalshi_post_order({"ticker": "T", "side": "yes", "action": "buy", "count": 1, "type": "limit", "yes_price": 41, "client_order_id": "abc"})
b1 = captured["body"]
print("YES 41c ->", b1["side"], b1["price"], "| url:", captured["url"][-40:], "| signed:", captured["signed_path"])
assert b1["side"] == "bid" and b1["price"] == "0.4100", b1

# NO at 55c -> ask @ 0.4500 (mirror!)
code, _ = mc.kalshi_post_order({"ticker": "T", "side": "no", "action": "buy", "count": 1, "type": "limit", "no_price": 55, "client_order_id": "def"})
b2 = captured["body"]
print("NO  55c ->", b2["side"], b2["price"])
assert b2["side"] == "ask" and b2["price"] == "0.4500", b2

# NO at 5c -> ask @ 0.9500
code, _ = mc.kalshi_post_order({"ticker": "T", "side": "no", "action": "buy", "count": 1, "type": "limit", "no_price": 5, "client_order_id": "ghi"})
b3 = captured["body"]
print("NO   5c ->", b3["side"], b3["price"])
assert b3["side"] == "ask" and b3["price"] == "0.9500", b3

assert captured["url"].endswith("/portfolio/events/orders")
assert captured["signed_path"] == "/trade-api/v2/portfolio/events/orders"
assert captured["body"]["time_in_force"] == "good_till_canceled"
print("MIRROR FIX VERIFIED — no/ask prices mirrored, yes/bid direct, V2 path correct")
