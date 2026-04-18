"""서버 재시작 시 자동 마이그레이션 검증.

initialize()가 기존 DB(신규 컬럼 없음) 상태에서도 ALTER TABLE로 자동 추가해야 한다.
이게 없으면 운영자가 매번 SQL 스크립트를 수동으로 돌려야 함.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from cryptobot.data.database import Database


@pytest.fixture
def legacy_db_path():
    """신규 컬럼이 없는 옛 스키마 DB 파일 생성."""
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / "legacy.db"
    conn = sqlite3.connect(str(path))
    # 옛 스키마 — before/after/impact_score/scope 없음
    conn.executescript("""
        CREATE TABLE llm_decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            model TEXT NOT NULL,
            input_news_summary TEXT,
            output_market_state TEXT
        );
        CREATE TABLE news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            title TEXT NOT NULL,
            collected_at DATETIME NOT NULL
        );
    """)
    conn.commit()
    conn.close()
    return path


def test_initialize_adds_llm_decisions_before_after(legacy_db_path):
    """initialize()가 llm_decisions에 before_snapshot_json / after_snapshot_json 컬럼 추가."""
    # 실행 전 검증
    conn = sqlite3.connect(str(legacy_db_path))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("SELECT before_snapshot_json FROM llm_decisions LIMIT 1")
    conn.close()

    # initialize() 실행 → 자동 마이그레이션 발동
    db = Database(legacy_db_path)
    db.initialize()
    try:
        # 컬럼 존재 확인 (OperationalError 안 나면 성공)
        db.execute("SELECT before_snapshot_json, after_snapshot_json FROM llm_decisions LIMIT 1").fetchone()
    finally:
        db.close()


def test_initialize_adds_news_articles_impact_scope(legacy_db_path):
    """initialize()가 news_articles에 impact_score / scope 컬럼 추가."""
    conn = sqlite3.connect(str(legacy_db_path))
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("SELECT impact_score FROM news_articles LIMIT 1")
    conn.close()

    db = Database(legacy_db_path)
    db.initialize()
    try:
        db.execute("SELECT impact_score, scope FROM news_articles LIMIT 1").fetchone()
    finally:
        db.close()


def test_initialize_idempotent(legacy_db_path):
    """initialize()를 여러 번 호출해도 에러 없이 동작 (중복 ALTER 방지)."""
    db = Database(legacy_db_path)
    db.initialize()  # 1회차: 컬럼 추가
    db.initialize()  # 2회차: 이미 있으므로 스킵
    db.initialize()  # 3회차
    try:
        db.execute("SELECT before_snapshot_json FROM llm_decisions LIMIT 1").fetchone()
        db.execute("SELECT impact_score FROM news_articles LIMIT 1").fetchone()
    finally:
        db.close()
