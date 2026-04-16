-- 거래 정합성 검증 컬럼 추가 마이그레이션
-- 실행: sqlite3 data/cryptobot.db < scripts/migrate_add_reconciliation.sql

ALTER TABLE trades ADD COLUMN order_uuid TEXT;
ALTER TABLE trades ADD COLUMN reconciled INTEGER DEFAULT 0;  -- 0: 미검증, 1: 일치, 2: 보정됨
ALTER TABLE trades ADD COLUMN reconciled_at DATETIME;
