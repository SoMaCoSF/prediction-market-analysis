import time
from typing import Dict, Any, Optional

def handle_fill_and_reprice(fill_event: Dict[str, Any], client: Optional[Any] = None) -> Dict[str, Any]:
    """
    Triggers on fill (0x3A7). Spawns a child exit ask (0x3A5) at fill + 15 cents.
    Tracks lineage using GYST UUIDv8 deterministic parent-child hashing.
    """
    parent_uuid = fill_event["uuid"]
    market_ticker = fill_event["ticker"]
    fill_price = fill_event["signal_price"]  # 0.0 - 1.0 (16-bit float equivalent)
    ttl_seconds = fill_event.get("ttl", 540)

    # 1. Enforce strict exit condition: Fill + 15 cents (capped at 99 cents)
    target_exit_price = min(round(fill_price + 0.15, 2), 0.99)
    
    # Guard: Don't place exits if window has less than 120s remaining
    if ttl_seconds <= 120:
        print(f"[REPRICE SKIPPED] Market {market_ticker} TTL too low ({ttl_seconds}s). Holding to settle/manual.")
        return {"status": "SKIPPED_LOW_TTL"}

    print(f"[REPRICE TRIGGERED] Parent Fill: {fill_price:.2f} -> Exit Target: {target_exit_price:.2f}")

    # 2. Dry-Run Check: If no API client is passed, simulate execution success
    if client is None:
        print(f"[DRY-RUN SIMULATION] Would submit Ask @ ${target_exit_price:.2f} for {market_ticker}")
        return {
            "status": "SIMULATED_SUCCESS",
            "exit_price": target_exit_price,
            "simulated_order_id": f"ack_{parent_uuid['low_42_hex']}"
        }

    # 3. Live Order Submission to Kalshi V2
    try:
        # Note: YES asks close out long YES positions cleanly
        response = client.place_order(
            ticker=market_ticker,
            action="sell",  # Closing out long YES position
            type="limit",
            yes_price=int(target_exit_price * 100),
            count=fill_event["count"],
            client_order_id=parent_uuid["low_42_hex"]  # Bitwise echo for O(1) reconciliation
        )
        return {"status": "EXIT_PLACED", "exit_price": target_exit_price, "order": response}
    except Exception as e:
        print(f"[REPRICE ERROR] Failed to place exit ask: {e}")
        return {"status": "FAILED", "error": str(e)}

if __name__ == "__main__":
    # Standard mock payload for dry-run verification
    mock_fill = {
        "uuid": {"low_42_hex": "1e14743d7d7"},
        "ticker": "KXBTC-26AUG02-T1415",
        "signal_price": 0.41,
        "ttl": 500,
        "count": 1
    }
    
    print("--- RUNNING REPRICE ENGINE TEST ---")
    result = handle_fill_and_reprice(mock_fill, client=None)
    print("Result:", result)