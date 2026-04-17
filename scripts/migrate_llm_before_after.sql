-- llm_decisions에 before/after 스냅샷 전용 컬럼 추가 (#171)
-- 기존에는 input_news_summary를 재사용해 저장 → 이름과 내용 불일치로 디버깅 혼란
-- 실행: sqlite3 data/cryptobot.db < scripts/migrate_llm_before_after.sql
-- 재실행 안전 (IF NOT EXISTS 대신 SQLite는 ALTER 실패 시 무시하지 않으므로 수동 확인)

ALTER TABLE llm_decisions ADD COLUMN before_snapshot_json TEXT;
ALTER TABLE llm_decisions ADD COLUMN after_snapshot_json TEXT;
