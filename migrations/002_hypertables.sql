-- Crypto-trading hypertables. Idempotent.

CREATE TABLE IF NOT EXISTS klines (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_price NUMERIC(20,8) NOT NULL,
    high_price NUMERIC(20,8) NOT NULL,
    low_price NUMERIC(20,8) NOT NULL,
    close_price NUMERIC(20,8) NOT NULL,
    volume NUMERIC(30,8) NOT NULL,
    trades INTEGER NOT NULL,
    is_closed BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (time, symbol, timeframe)
);
SELECT create_hypertable('klines', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_klines_symbol_timeframe_time
    ON klines (symbol, timeframe, time DESC);

CREATE TABLE IF NOT EXISTS tickers (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    price NUMERIC(20,8) NOT NULL,
    bid NUMERIC(20,8),
    ask NUMERIC(20,8),
    bid_qty NUMERIC(30,8),
    ask_qty NUMERIC(30,8),
    high_24h NUMERIC(20,8),
    low_24h NUMERIC(20,8),
    volume_24h NUMERIC(30,8),
    change_24h NUMERIC(10,4),
    PRIMARY KEY (time, symbol)
);
SELECT create_hypertable('tickers', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_tickers_symbol_time
    ON tickers (symbol, time DESC);

CREATE TABLE IF NOT EXISTS trades (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    price NUMERIC(20,8) NOT NULL,
    quantity NUMERIC(30,8) NOT NULL,
    side TEXT NOT NULL,
    is_maker BOOLEAN NOT NULL,
    PRIMARY KEY (time, symbol, trade_id)
);
SELECT create_hypertable('trades', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_trades_symbol_time
    ON trades (symbol, time DESC);

CREATE TABLE IF NOT EXISTS funding_rates (
    time TIMESTAMPTZ NOT NULL,
    symbol TEXT NOT NULL,
    funding_rate NUMERIC(10,8) NOT NULL,
    mark_price NUMERIC(20,8) NOT NULL,
    index_price NUMERIC(20,8) NOT NULL,
    next_funding_time TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (time, symbol)
);
SELECT create_hypertable('funding_rates', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_funding_symbol_time
    ON funding_rates (symbol, time DESC);

-- Optional retention / aggregation. Uncomment in production.
-- SELECT add_retention_policy('klines', INTERVAL '5 years');
-- SELECT add_retention_policy('tickers', INTERVAL '90 days');
-- SELECT add_retention_policy('trades', INTERVAL '180 days');
