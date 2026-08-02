-- file_id: SOM-SQL-0915-v1.0.0 name: ledger_schema.sql description: UUID-native trading ledger — every order/fill/settlement is a GYST UUIDv8; spawn-tree P&L by parent_uuid walk; reconciliation via low-42 bitmask project_id: PREDICTION-MARKET-ANALYSIS category: sql tags: [ledger, uuid, gyst, kalshi, trading] created: 2026-08-02 version: 1.0.0 agent_id: HERMES-AGENT
-- Idempotent: CREATE IF NOT EXISTS only. No drops. Safe to re-apply.

-- Orders: each order is a CHILD UUID (0x3A4) spawned under its market UUID.
CREATE TABLE IF NOT EXISTS uuid_orders (
    uuid              TEXT PRIMARY KEY,          -- GYST UUIDv8 string
    uuid_hi           BIGINT NOT NULL,           -- signed hi 64 (bitmask-routable)
    uuid_lo           BIGINT NOT NULL,           -- signed lo 64; low-42 = client_order_id
    client_order_id   TEXT NOT NULL UNIQUE,      -- = hex of low-42 tail (reconciliation key, NO lookup table)
    parent_uuid       TEXT,                      -- market UUID this order spawns under
    ticker            TEXT NOT NULL,
    side              TEXT NOT NULL,             -- yes / no
    price_cents       INT NOT NULL,              -- limit price 1..99
    count             INT NOT NULL,              -- contracts
    status            TEXT NOT NULL DEFAULT 'minted',  -- minted/submitted/ack/partial/filled/canceled/settled
    mode              TEXT NOT NULL DEFAULT 'paper',   -- paper / live
    exchange_order_id TEXT,                      -- set on exchange ack (live mode)
    ts                BIGINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_orders_lo42   ON uuid_orders ((uuid_lo & 4398046511103)); -- 2^42-1
CREATE INDEX IF NOT EXISTS idx_orders_parent ON uuid_orders (parent_uuid);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON uuid_orders (ticker);

-- Fills: each fill is a CHILD UUID (0x3A7) spawned under its order UUID.
CREATE TABLE IF NOT EXISTS uuid_fills (
    uuid              TEXT PRIMARY KEY,
    uuid_hi           BIGINT NOT NULL,
    uuid_lo           BIGINT NOT NULL,
    parent_uuid       TEXT NOT NULL REFERENCES uuid_orders(uuid),  -- spawn edge: fill -> order
    price_cents       INT NOT NULL,
    count             INT NOT NULL,
    fee_cents         INT NOT NULL DEFAULT 0,
    exchange_fill_id  TEXT,
    ts                BIGINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fills_parent ON uuid_fills (parent_uuid);

-- Positions: net exposure per ticker/side (paper + live).
CREATE TABLE IF NOT EXISTS uuid_positions (
    ticker             TEXT NOT NULL,
    side               TEXT NOT NULL,
    market_uuid        TEXT,
    net_count          BIGINT NOT NULL DEFAULT 0,
    avg_price_cents    DOUBLE PRECISION NOT NULL DEFAULT 0,
    realized_pnl_cents BIGINT NOT NULL DEFAULT 0,
    updated_ts         BIGINT NOT NULL,
    PRIMARY KEY (ticker, side)
);

-- Marks/settlements: 0x3AA mark / 0x3A9 settle events as UUIDs (audit trail).
CREATE TABLE IF NOT EXISTS uuid_marks (
    uuid              TEXT PRIMARY KEY,
    uuid_hi           BIGINT NOT NULL,
    uuid_lo           BIGINT NOT NULL,
    parent_uuid       TEXT NOT NULL,             -- market UUID
    ticker            TEXT NOT NULL,
    mark_cents        INT NOT NULL,              -- settlement/mark price 0..100
    kind              TEXT NOT NULL,             -- settle / mark
    ts                BIGINT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- P&L rollup: pure SQL walk of the spawn tree (market -> orders -> fills).
CREATE OR REPLACE VIEW uuid_pnl AS
SELECT o.parent_uuid AS market_uuid,
       o.ticker,
       count(DISTINCT o.uuid)              AS orders,
       coalesce(sum(f.count), 0)           AS filled_contracts,
       coalesce(sum(f.count * f.price_cents), 0) AS notional_cents,
       coalesce(sum(f.fee_cents), 0)       AS fees_cents
FROM uuid_orders o
LEFT JOIN uuid_fills f ON f.parent_uuid = o.uuid
GROUP BY o.parent_uuid, o.ticker;
