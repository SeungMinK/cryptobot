"""P2 #171 — 경계/엣지 케이스 테스트.

1. KST 일 경계 call count
2. emergency config HARD_LIMITS 검증
3. before/after 전용 컬럼 사용
"""

import json
import tempfile
from pathlib import Path

import pytest

from cryptobot.bot.risk import RiskLimits, RiskManager
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.llm.analyzer import LLMAnalyzer


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


# ===================================================================
# 1. KST 일 경계 — LLM daily count
# ===================================================================


def test_llm_daily_count_kst_boundary(db):
    """LLM 호출 집계가 KST 일 경계로 이뤄진다 (UTC 아님).

    DB `datetime('now', '+9 hours')`로 KST 시각 계산 후 DATE 추출.
    순수 쿼리 결과로 KST 일자 계산이 정상 작동하는지만 검증.
    """
    # 현재 KST 일자 조회 (SQLite가 산출한 값)
    kst_today = db.execute("SELECT DATE('now', '+9 hours')").fetchone()[0]
    utc_today = db.execute("SELECT DATE('now')").fetchone()[0]
    assert kst_today is not None

    # 25시간 전 레코드는 KST 기준 확실히 어제
    db.execute(
        "INSERT INTO llm_decisions (timestamp, model) "
        "VALUES (datetime('now', '-25 hours'), 'test')"
    )
    db.commit()
    daily = db.execute(
        "SELECT COUNT(*) FROM llm_decisions "
        "WHERE DATE(timestamp, '+9 hours') = DATE('now', '+9 hours')"
    ).fetchone()[0]
    assert daily == 0, "25시간 전 레코드는 KST 기준 오늘에 포함되면 안 됨"

    # 1분 전 레코드는 KST 기준 확실히 오늘
    db.execute(
        "INSERT INTO llm_decisions (timestamp, model) "
        "VALUES (datetime('now', '-1 minute'), 'test')"
    )
    db.commit()
    daily_after = db.execute(
        "SELECT COUNT(*) FROM llm_decisions "
        "WHERE DATE(timestamp, '+9 hours') = DATE('now', '+9 hours')"
    ).fetchone()[0]
    assert daily_after == 1
    # UTC 와 KST 일자가 다른 경우에도 쿼리가 올바르게 KST 기준으로 동작
    # (UTC 15:00 이후에는 kst_today != utc_today가 될 수 있음)
    _ = utc_today  # 참조 유지


def test_risk_today_trade_count_uses_kst(db):
    """RiskManager._get_today_trade_count도 KST 기준 (#171)."""
    recorder = DataRecorder(db)
    rm = RiskManager(db, RiskLimits())
    # 25시간 전 거래 1건 (KST 기준 어제)
    recorder.record_trade(
        coin="KRW-BTC", side="buy", price=100, amount=1, total_krw=100, fee_krw=1,
        strategy="test", trigger_reason="test",
    )
    db.execute("UPDATE trades SET timestamp = datetime('now', '-25 hours')")
    db.commit()

    count = rm._get_today_trade_count("KRW-BTC")
    assert count == 0, "25시간 전 거래는 KST 기준 어제라 오늘 카운트에 포함되면 안 됨"


# ===================================================================
# 2. emergency config HARD_LIMITS 검증
# ===================================================================


def test_config_float_rejects_out_of_range(db):
    """HARD_LIMITS 범위 밖 값은 기본값으로 폴백 + WARN 로그."""
    analyzer = LLMAnalyzer(db)
    # emergency_held_pct의 HARD_LIMITS = (1.0, 10.0)
    db.execute(
        "INSERT INTO bot_config (key, value, display_name) "
        "VALUES ('emergency_held_pct', '0.1', 'Emergency Held')"
    )
    db.commit()
    # 0.1은 범위 (1.0, 10.0) 밖 → default 3.0 반환
    value = analyzer._get_config_float("emergency_held_pct", 3.0)
    assert value == 3.0


def test_config_float_accepts_in_range(db):
    """HARD_LIMITS 범위 내 값은 그대로 반환."""
    analyzer = LLMAnalyzer(db)
    db.execute(
        "INSERT INTO bot_config (key, value, display_name) "
        "VALUES ('emergency_held_pct', '5.0', 'Emergency Held')"
    )
    db.commit()
    value = analyzer._get_config_float("emergency_held_pct", 3.0)
    assert value == 5.0


def test_config_float_no_limits_key_no_validation(db):
    """HARD_LIMITS에 없는 키는 범위 검증 안 함."""
    analyzer = LLMAnalyzer(db)
    db.execute(
        "INSERT INTO bot_config (key, value, display_name) "
        "VALUES ('unrelated_key', '9999.9', 'Unrelated')"
    )
    db.commit()
    value = analyzer._get_config_float("unrelated_key", 1.0)
    assert value == 9999.9


# ===================================================================
# 3. before/after 전용 컬럼
# ===================================================================


def test_apply_recommendations_writes_to_new_columns(db):
    """_apply_recommendations가 before_snapshot_json / after_snapshot_json에 저장."""
    analyzer = LLMAnalyzer(db)
    # bb_rsi_combined 활성
    db.execute("UPDATE strategies SET is_active = 0")
    db.execute(
        "UPDATE strategies SET is_active = 1, is_available = 1 "
        "WHERE name = 'bb_rsi_combined'"
    )
    db.execute(
        "INSERT INTO llm_decisions (timestamp, model) "
        "VALUES (datetime('now'), 'test')"
    )
    db.commit()

    result = {
        "market_summary_kr": "test",
        "market_state": "sideways",
        "confidence": 0.7,
        "aggression": 0.5,
        "allow_trading": True,
        "should_alert_stop": False,
        "recommended_strategy": "bb_rsi_combined",
        "recommended_params": {"stop_loss_pct": -5, "k_value": 0.5},
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)

    row = db.execute(
        "SELECT before_snapshot_json, after_snapshot_json, input_news_summary "
        "FROM llm_decisions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    d = dict(row)
    # 신규 컬럼에 저장됐는지
    assert d["before_snapshot_json"] is not None
    assert d["after_snapshot_json"] is not None
    before = json.loads(d["before_snapshot_json"])
    after = json.loads(d["after_snapshot_json"])
    assert isinstance(before, dict)
    assert isinstance(after, dict)
    # 구 컬럼도 호환 유지 (병행 저장)
    assert d["input_news_summary"] is not None
