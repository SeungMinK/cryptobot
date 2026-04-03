"""database 모듈 테스트."""

import tempfile
from pathlib import Path

from cryptobot.data.database import Database


def test_initialize_creates_tables():
    """DB 초기화 시 모든 테이블이 생성되는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with Database(db_path) as db:
            db.initialize()

            tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            table_names = [t["name"] for t in tables]

            assert "market_snapshots" in table_names
            assert "trade_signals" in table_names
            assert "trades" in table_names
            assert "strategy_params" in table_names
            assert "daily_reports" in table_names
            assert "llm_decisions" in table_names


def test_default_strategy_params():
    """초기화 시 기본 전략 파라미터가 삽입되는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with Database(db_path) as db:
            db.initialize()

            row = db.execute("SELECT * FROM strategy_params WHERE source='default'").fetchone()
            assert row is not None
            assert row["k_value"] == 0.5
            assert row["stop_loss_pct"] == -5.0
            assert row["trailing_stop_pct"] == -3.0
            assert row["max_positions"] == 1


def test_initialize_idempotent():
    """initialize를 두 번 호출해도 데이터가 중복되지 않는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with Database(db_path) as db:
            db.initialize()
            db.initialize()

            count = db.execute("SELECT COUNT(*) FROM strategy_params").fetchone()[0]
            assert count == 1


def test_insert_and_query():
    """기본적인 INSERT/SELECT가 동작하는지 확인."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        with Database(db_path) as db:
            db.initialize()

            db.execute(
                "INSERT INTO market_snapshots (btc_price, market_state) VALUES (?, ?)",
                (50000000.0, "bullish"),
            )
            db.commit()

            row = db.execute("SELECT * FROM market_snapshots").fetchone()
            assert row["btc_price"] == 50000000.0
            assert row["market_state"] == "bullish"
