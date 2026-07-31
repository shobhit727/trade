-- TimescaleDB extension + crypto-trading schema.
--
-- Apply order:
--   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f migrations/001_extension.sql
--   psql -h $DB_HOST -U $DB_USER -d $DB_NAME -f migrations/002_hypertables.sql
--
-- Or simply run both; each statement is idempotent.

CREATE EXTENSION IF NOT EXISTS timescaledb;
