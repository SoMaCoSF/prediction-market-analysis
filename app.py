import time
import sys
from typing import Dict, Any, List

class TradeControlApp:
    def __init__(self):
        # 1. State Tracking (Exchange & Collateral Accounts)
        self.accounts = {
            "kalshi_primary": {
                "balance": 18.40,  # Hard-coded from current honest ledger
                "reserved": 5.00,   # Locked for long-game MLB futures
                "available": 13.40,
                "status": "ACTIVE"
            },
            "kraken_drift_feed": {
                "balance": 100.00,
                "status": "CONNECTED"
            }
        }
        self.is_running = False
        self.total_realized_pnl = 0.0

    def get_account_summary(self) -> None:
        """Prints high-level account status across all integrated platforms."""
        print("\n=================== SOMACO // TRADE CONTROL ===================")
        for acc, data in self.accounts.items():
            print(f"[{acc.upper()}] Status: {data['status']} | Balance: ${data['balance']:.2f}")
        print("===============================================================\n")

    def reprice_exit_check(self, fill_event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates +15c target exit and validates safety constraints before execution.
        """
        fill_price = fill_event["signal_price"]
        ttl_seconds = fill_event.get("ttl", 540)
        target_exit_price = min(round(fill_price + 0.15, 2), 0.99)

        # Safety Gate: Hard TTL Cutoff
        if ttl_seconds <= 120:
            return {"status": "SKIPPED_LOW_TTL", "reason": f"TTL {ttl_seconds}s <= 120s"}

        # Safety Gate: Available Capital Check ($18.40 Protection)
        cost = fill_event.get("count", 1) * fill_price
        if cost > self.accounts["kalshi_primary"]["available"]:
            return {"status": "BLOCKED_BY_SAFETY_GATE", "reason": "Insufficient unlocked capital"}

        return {
            "status": "READY_TO_EXECUTE",
            "target_exit": target_exit_price,
            "uuid_tail": fill_event["uuid"]["low_42_hex"]
        }

    def start_loop(self, poll_interval_sec: float = 3.0):
        """
        Main execution tick loop that runs indefinitely, checking for market setups 
        and maintaining exit discipline.
        """
        self.is_running = True
        print(f"[STARTING ENGINE LOOP] Polling every {poll_interval_sec} seconds... Press Ctrl+C to stop.")
        
        tick_count = 0
        try:
            while self.is_running:
                tick_count += 1
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                
                # Mock market signal check (In production, replace with live WS/API polling)
                mock_signal = {
                    "uuid": {"low_42_hex": "1e14743d7d7"},
                    "ticker": f"KXBTC-26AUG02-T{timestamp.replace(':', '')[:4]}",
                    "signal_price": 0.41,
                    "ttl": 450,
                    "count": 1
                }

                # Evaluate Signal
                evaluation = self.reprice_exit_check(mock_signal)
                
                print(f"[{timestamp}] TICK #{tick_count:04d} | Market: {mock_signal['ticker']} | Result: {evaluation['status']}")
                
                if evaluation["status"] == "READY_TO_EXECUTE":
                    print(f"   └── [ORDER] Ask Target: ${evaluation['target_exit']:.2f} | ID: {evaluation['uuid_tail']}")

                time.sleep(poll_interval_sec)

        except KeyboardInterrupt:
            print("\n[STOPPING ENGINE LOOP] Shutdown signal received. Exiting safely...")
            self.is_running = False

if __name__ == "__main__":
    app = TradeControlApp()
    app.get_account_summary()
    app.start_loop(poll_interval_sec=2.0)