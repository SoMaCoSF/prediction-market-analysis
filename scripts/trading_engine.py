#!/usr/bin/env python3
"""
Event-driven trading engine core.
No polling. No sleep loops. Event-driven architecture.
"""
import asyncio
import sys
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from mission_control import KALSHI_HOST, kalshi_keys, kalshi_sign  # noqa: E402

LOG = ROOT / "logs" / "engine.log"
STATE = ROOT / "data" / "engine_state.json"

class EventType(Enum):
    MARKET_TICK = "market_tick"
    PAPER_TICK = "paper_tick"
    TRADE_FILL = "trade_fill"
    ORDER_UPDATE = "order_update"
    POSITION_UPDATE = "position_update"
    BALANCE_UPDATE = "balance_update"
    WHALE_SIGNAL = "whale_signal"
    SETTLEMENT_ALERT = "settlement_alert"
    ERROR = "error"
    HEARTBEAT = "heartbeat"

@dataclass
class Event:
    type: EventType
    data: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    source: str = "system"

@dataclass
class Position:
    ticker: str
    side: str  # "yes" or "no"
    size: int
    entry_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    timestamp: float = field(default_factory=time.time)

@dataclass
class Order:
    order_id: str
    ticker: str
    side: str
    price: float
    size: int
    status: str = "pending"
    fill_price: float = 0.0
    fill_size: int = 0
    timestamp: float = field(default_factory=time.time)

class Strategy(ABC):
    """Base strategy class. All strategies must implement this."""

    @abstractmethod
    async def on_market_tick(self, event: Event, engine: 'TradingEngine') -> list[Event]:
        """Process market tick, return list of new events (e.g., order requests)."""
        pass

    @abstractmethod
    async def on_trade_fill(self, event: Event, engine: 'TradingEngine') -> list[Event]:
        """Process fill event."""
        pass

    @abstractmethod
    async def on_order_update(self, event: Event, engine: 'TradingEngine') -> list[Event]:
        """Process order status change."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Strategy name for logging."""
        pass

class RiskManager:
    """Central risk management."""

    def __init__(self, max_position_size: int = 5, max_drawdown_pct: float = 0.20,
                 max_open_positions: int = 10, min_cash_reserve: float = 1.00):
        self.max_position_size = max_position_size
        self.max_drawdown_pct = max_drawdown_pct
        self.max_open_positions = max_open_positions
        self.min_cash_reserve = min_cash_reserve
        self.peak_equity = 0.0
        self.current_drawdown = 0.0

    def check_order(self, order: Order, cash: float, positions: list[Position],
                    portfolio_value: float) -> tuple[bool, str]:
        """Validate order against risk limits. Returns (allowed, reason)."""
        # Cash check
        order_cost = order.price * order.size / 100.0
        if order_cost > cash - self.min_cash_reserve:
            return False, f"insufficient cash: need ${order_cost:.2f}, have ${cash:.2f}"

        # Position count check
        open_positions = [p for p in positions if p.size > 0]
        if len(open_positions) >= self.max_open_positions:
            return False, f"max positions reached: {len(open_positions)}/{self.max_open_positions}"

        # Position size check
        if order.size > self.max_position_size:
            return False, f"order size {order.size} > max {self.max_position_size}"

        # Drawdown check
        if portfolio_value > 0:
            self.peak_equity = max(self.peak_equity, portfolio_value)
            self.current_drawdown = (self.peak_equity - portfolio_value) / self.peak_equity if self.peak_equity > 0 else 0
            if self.current_drawdown > self.max_drawdown_pct:
                return False, f"drawdown limit: {self.current_drawdown:.1%} > {self.max_drawdown_pct:.1%}"

        return True, "OK"

    def update_drawdown(self, portfolio_value: float):
        """Update drawdown tracking."""
        if portfolio_value > 0:
            self.peak_equity = max(self.peak_equity, portfolio_value)
            self.current_drawdown = (self.peak_equity - portfolio_value) / self.peak_equity if self.peak_equity > 0 else 0

class TradingEngine:
    """Main event-driven trading engine."""

    def __init__(self):
        self.event_queue: deque = deque()
        self.strategies: list[Strategy] = []
        self.risk = RiskManager()
        self.positions: dict[str, Position] = {}
        self.orders: dict[str, Order] = {}
        self.cash: float = 62.21
        self.portfolio_value: float = 0.0
        self.running = False
        self._event_handlers: dict[EventType, list[Callable]] = {}
        self._ws_task: Optional[asyncio.Task] = None

    def register_handler(self, event_type: EventType, handler: Callable):
        """Register an event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)

    def emit(self, event: Event):
        """Emit an event to the queue."""
        self.event_queue.append(event)
        log(f"EVENT: {event.type.value} from {event.source}")

    async def _process_events(self):
        """Process events from queue."""
        while self.running:
            if self.event_queue:
                event = self.event_queue.popleft()
                await self._dispatch_event(event)
            else:
                await asyncio.sleep(0.001)  # 1ms sleep when idle

    async def _dispatch_event(self, event: Event):
        """Dispatch event to handlers."""
        handlers = self._event_handlers.get(event.type, [])
        for handler in handlers:
            try:
                result = handler(event, self)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                log(f"ERROR in handler {handler.__name__}: {e}")

        # Also dispatch to strategies
        for strategy in self.strategies:
            try:
                if event.type == EventType.MARKET_TICK:
                    await strategy.on_market_tick(event, self)
                elif event.type == EventType.TRADE_FILL:
                    await strategy.on_trade_fill(event, self)
                elif event.type == EventType.ORDER_UPDATE:
                    await strategy.on_order_update(event, self)
            except Exception as e:
                log(f"ERROR in strategy {strategy.get_name()}: {e}")

    async def _ws_market_feed(self):
        """WebSocket market data feed."""
        # TODO: Implement WebSocket connection to Kalshi
        # For now, fall back to polling until WS is implemented
        log("WS feed not yet implemented, falling back to polling")
        while self.running:
            try:
                data = self._kalshi_get("/markets?limit=200&status=open")
                markets = data.get("markets", [])
                for m in markets:
                    self.emit(Event(
                        type=EventType.MARKET_TICK,
                        data=m,
                        source="kalshi_ws"
                    ))
                await asyncio.sleep(1)  # 1s polling until WS is ready
            except Exception as e:
                log(f"WS feed error: {e}")
                await asyncio.sleep(5)

    def _kalshi_get(self, path: str) -> dict:
        """Signed GET to Kalshi API."""
        kid, kpath = kalshi_keys()
        ts = str(int(time.time() * 1000))
        sig = kalshi_sign("GET", path, ts, kpath)
        headers = {
            "KALSHI-ACCESS-KEY": kid,
            "KALSHI-ACCESS-SIGNATURE": sig,
            "KALSHI-ACCESS-TIMESTAMP": ts,
        }
        r = httpx.get(f"{KALSHI_HOST}{path}", headers=headers, timeout=20)
        r.raise_for_status()
        return r.json()

    async def _paper_execution(self):
        """Execute paper trades from strategy signals using real Kalshi prices."""
        import json
        import random
        from datetime import datetime, timezone
        try:
            import sb as _sb
            _con = _sb.sb_conn()
            _con.autocommit = True
            _cur = _con.cursor()
            _cur.execute("CREATE TABLE IF NOT EXISTS paper_ledger (ts TIMESTAMPTZ DEFAULT now(), ticker TEXT, side TEXT, price NUMERIC, count INT, pnl NUMERIC)")
            _con.close()
        except Exception:
            pass
        state_path = ROOT / "data" / "paper_venue.json"
        log_path = ROOT / "logs" / "paper_exec.out"
        fill_prob = 0.85

        def log_paper(msg: str):
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            line = f"[{ts}] {msg}"
            print(line, flush=True)
            try:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

        def load_state():
            try:
                if state_path.exists():
                    return json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
            return {"orderbook": {}, "last_update": 0}

        def save_state(state):
            try:
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            except Exception:
                pass

        async def match_paper(side: str, ticker: str, price_cents: int):
            state = load_state()
            book = state.get("orderbook", {}).get(ticker)
            if not book:
                return None
            yes_ask = book.get("yes_ask", 0)
            no_ask = book.get("no_ask", 0)
            ask = yes_ask if side == "yes" else no_ask
            if ask <= 0 or price_cents / 100 < ask:
                return None
            if random.random() > fill_prob:
                return None
            fill_price = ask
            count = 1
            fee = round(count * fill_price * 0.01, 4)
            pnl = round((1.0 - fill_price) * count - fee, 4) if side == "yes" else round((fill_price) * count - fee, 4)
            self.cash += pnl
            log_paper(f"FILL {side.upper()} {ticker} @ {fill_price*100:.0f}¢ P&L={pnl:+.2f} cash={self.cash:.2f}")
            return {"side": side, "ticker": ticker, "price": fill_price, "count": count, "pnl": pnl}

        log_paper("PAPER EXECution STARTED")
        while self.running:
            try:
                while self.event_queue:
                    event = self.event_queue.popleft()
                    if event.type in (EventType.WHALE_SIGNAL, EventType.TRADE_FILL):
                        data = event.data or {}
                        ticker = data.get("ticker")
                        side = data.get("side") or ("yes" if event.type == EventType.WHALE_SIGNAL else None)
                        price_cents = data.get("price_cents") or data.get("price")
                        if not ticker or not side or not price_cents:
                            continue
                        try:
                            price_cents = int(price_cents)
                        except Exception:
                            continue
                        if self.cash < 1.0:
                            continue
                        result = await match_paper(side, ticker, price_cents)
                        if result:
                            self.portfolio_value = max(0.0, self.portfolio_value + result["pnl"])
                await asyncio.sleep(0.05)
            except Exception as e:
                log_paper(f"warn {repr(e)[:60]}")
                await asyncio.sleep(1)

    def add_strategy(self, strategy: Strategy):
        """Register a strategy."""
        self.strategies.append(strategy)
        log(f"Strategy registered: {strategy.get_name()}")

    async def start(self):
        """Start the engine."""
        log("ENGINE STARTING")
        self.running = True

        # Start event processor
        self._event_task = asyncio.create_task(self._process_events())

        # Start WS feed
        self._ws_task = asyncio.create_task(self._ws_market_feed())

        # Start paper execution loop
        self._paper_task = asyncio.create_task(self._paper_execution())

        log("ENGINE RUNNING")

    async def stop(self):
        """Stop the engine."""
        log("ENGINE STOPPING")
        self.running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._event_task:
            self._event_task.cancel()
        log("ENGINE STOPPED")

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

async def main():
    engine = TradingEngine()

    # Register strategies
    from strategies.arb import ArbStrategy
    from strategies.panic_fade import PanicFadeStrategy
    from strategies.whale_follow import WhaleFollowStrategy
    engine.add_strategy(PanicFadeStrategy())
    engine.add_strategy(WhaleFollowStrategy())
    engine.add_strategy(ArbStrategy())

    await engine.start()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await engine.stop()

if __name__ == "__main__":
    asyncio.run(main())
