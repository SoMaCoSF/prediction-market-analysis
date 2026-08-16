"""
swarm_watcher.store
===================

Local SQLite store for the Up/Down Signal Swarm watcher.

Tables:
  wallets       — one row per observed wallet identity (GYST 0x3F0)
  ticks         — raw up/down market actions attributed to a wallet
  signals       — derived per-wallet swarm signals (GYST 0x3F2)
  swarm_events  — detected swarm transitions (flip / converge / diverge)
  wallet_profiles — materialized profile snapshots for dashboards

Local-only by design. No network. Path defaults to ./swarm_watcher.db and can
be overridden via SWARM_DB env or constructor arg.
"""

from __future__ import annotations

import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Iterable, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    wallet          TEXT PRIMARY KEY,
    gyst_uuid       TEXT NOT NULL,
    platform        TEXT NOT NULL DEFAULT 'kalshi',
    first_seen      REAL NOT NULL,
    last_seen       REAL NOT NULL,
    n_actions       INTEGER NOT NULL DEFAULT 0,
    up              INTEGER NOT NULL DEFAULT 0,
    down            INTEGER NOT NULL DEFAULT 0,
    bias            REAL NOT NULL DEFAULT 0.5,
    created_at      REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS ticks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    t           REAL NOT NULL,
    wallet      TEXT NOT NULL,
    market      TEXT NOT NULL,
    direction   INTEGER NOT NULL,   -- +1 up, -1 down
    size        REAL NOT NULL DEFAULT 1.0,
    price       REAL,
    FOREIGN KEY (wallet) REFERENCES wallets(wallet)
);
CREATE INDEX IF NOT EXISTS idx_ticks_wallet ON ticks(wallet);
CREATE INDEX IF NOT EXISTS idx_ticks_t ON ticks(t);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet      TEXT NOT NULL,
    gyst_uuid   TEXT NOT NULL,
    t           REAL NOT NULL,
    bias        REAL NOT NULL,
    bias_weighted REAL NOT NULL,
    market_bias REAL NOT NULL,
    contrarian  REAL NOT NULL,
    stickiness  REAL NOT NULL,
    polarity    TEXT NOT NULL,
    FOREIGN KEY (wallet) REFERENCES wallets(wallet)
);
CREATE INDEX IF NOT EXISTS idx_signals_wallet ON signals(wallet);

CREATE TABLE IF NOT EXISTS swarm_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    t           REAL NOT NULL,
    kind        TEXT NOT NULL,     -- FLIP / CONVERGE / DIVERGE / SWARM_UP / SWARM_DOWN
    wallet      TEXT,              -- nullable for market-wide events
    detail      TEXT,
    gyst_uuid   TEXT
);

CREATE TABLE IF NOT EXISTS wallet_profiles (
    wallet          TEXT PRIMARY KEY,
    n_actions       INTEGER NOT NULL,
    up              INTEGER NOT NULL,
    down            INTEGER NOT NULL,
    bias            REAL NOT NULL,
    bias_weighted   REAL NOT NULL,
    market_bias     REAL NOT NULL,
    contrarian      REAL NOT NULL,
    stickiness      REAL NOT NULL,
    divergence_vs_market REAL NOT NULL,
    updated_at      REAL NOT NULL,
    FOREIGN KEY (wallet) REFERENCES wallets(wallet)
);
"""

DEFAULT_DB = os.environ.get("SWARM_DB", os.path.join(os.path.dirname(__file__), "swarm_watcher.db"))


class WalletStore:
    def __init__(self, path: str = DEFAULT_DB):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    @contextmanager
    def tx(self):
        cur = self.conn.cursor()
        try:
            yield cur
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # -- wallets -----------------------------------------------------------
    def upsert_wallet(self, wallet: str, gyst_uuid: str, platform: str = "kalshi", t: Optional[float] = None):
        t = t if t is not None else time.time()
        with self.tx() as cur:
            cur.execute(
                """INSERT INTO wallets (wallet, gyst_uuid, platform, first_seen, last_seen, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(wallet) DO UPDATE SET last_seen=excluded.last_seen""",
                (wallet, gyst_uuid, platform, t, t, t),
            )

    def get_wallet(self, wallet: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute("SELECT * FROM wallets WHERE wallet=?", (wallet,))
        return cur.fetchone()

    def all_wallets(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM wallets ORDER BY last_seen DESC"))

    # -- ticks -------------------------------------------------------------
    def add_tick(self, t: float, wallet: str, market: str, direction: int, size: float = 1.0, price: Optional[float] = None):
        with self.tx() as cur:
            cur.execute(
                "INSERT INTO ticks (t, wallet, market, direction, size, price) VALUES (?,?,?,?,?,?)",
                (t, wallet, market, direction, size, price),
            )
            # maintain wallet rollup
            cur.execute(
                """UPDATE wallets SET n_actions=n_actions+1,
                                  up=up+(?=1),
                                  down=down+(?=-1),
                                  last_seen=?
                   WHERE wallet=?""",
                (direction, direction, t, wallet),
            )
            cur.execute(
                "UPDATE wallets SET bias = CASE WHEN (up+down)=0 THEN 0.5 ELSE CAST(up AS REAL)/(up+down) END WHERE wallet=?",
                (wallet,),
            )

    def ticks_for(self, wallet: str) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM ticks WHERE wallet=? ORDER BY t", (wallet,)))

    def all_ticks(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM ticks ORDER BY t"))

    # -- signals -----------------------------------------------------------
    def add_signal(self, wallet: str, gyst_uuid: str, t: float, profile: dict):
        with self.tx() as cur:
            cur.execute(
                """INSERT INTO signals (wallet, gyst_uuid, t, bias, bias_weighted, market_bias, contrarian, stickiness, polarity)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (wallet, gyst_uuid, t, profile["bias"], profile["bias_weighted"],
                 profile["market_bias"], profile["contrarian"], profile["stickiness"], profile["polarity"]),
            )

    # -- events ------------------------------------------------------------
    def add_event(self, t: float, kind: str, wallet: Optional[str], detail: str, gyst_uuid: Optional[str] = None):
        with self.tx() as cur:
            cur.execute(
                "INSERT INTO swarm_events (t, kind, wallet, detail, gyst_uuid) VALUES (?,?,?,?,?)",
                (t, kind, wallet, detail, gyst_uuid),
            )

    def events(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM swarm_events ORDER BY t DESC LIMIT 200"))

    # -- profiles ----------------------------------------------------------
    def save_profile(self, profile: dict):
        with self.tx() as cur:
            cur.execute(
                """INSERT INTO wallet_profiles
                   (wallet, n_actions, up, down, bias, bias_weighted, market_bias, contrarian, stickiness, divergence_vs_market, updated_at)
                   VALUES (:wallet,:n_actions,:up,:down,:bias,:bias_weighted,:market_bias,:contrarian,:stickiness,:divergence_vs_market,:updated_at)
                   ON CONFLICT(wallet) DO UPDATE SET
                     n_actions=excluded.n_actions, up=excluded.up, down=excluded.down,
                     bias=excluded.bias, bias_weighted=excluded.bias_weighted,
                     market_bias=excluded.market_bias, contrarian=excluded.contrarian,
                     stickiness=excluded.stickiness, divergence_vs_market=excluded.divergence_vs_market,
                     updated_at=excluded.updated_at""",
                {**profile, "updated_at": time.time()},
            )

    def profiles(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM wallet_profiles ORDER BY ABS(divergence_vs_market) DESC"))

    def close(self):
        self.conn.close()
