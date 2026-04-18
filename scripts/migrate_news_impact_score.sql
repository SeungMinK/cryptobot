-- 뉴스 impact_score/scope 추가 (#154)
-- 기존 데이터는 NULL로 시작. 신규 수집부터 규칙 기반으로 자동 태깅.
-- 실행: sqlite3 data/cryptobot.db < scripts/migrate_news_impact_score.sql

ALTER TABLE news_articles ADD COLUMN impact_score INTEGER;
ALTER TABLE news_articles ADD COLUMN scope TEXT;
