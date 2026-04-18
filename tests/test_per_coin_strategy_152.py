"""#152 — 코인별 개별 전략 배정 꼼꼼한 시뮬레이션 테스트.

실제 LLM 호출 없이 다음 시나리오를 전부 검증:

A. Repository 기본 동작
B. 진동 방지 가드 (min_hold_minutes)
C. 보유 포지션 중 전략 교체 금지
D. 유효성 검증 (비존재 전략, 빈 spec, dict 아닌 값)
E. apply_bulk — LLM 응답 일괄 적용
F. _apply_recommendations 통합 — coin_strategies 파싱
G. StrategySelector — assignment 우선, 없으면 default 폴백
H. 파라미터 오버라이드 복원 (_orig_extra)
I. 토큰 비용 시뮬레이션 (회귀 방지용)
J. 프롬프트 스펙 포함 검증
"""

import json
import sqlite3
import tempfile
from pathlib import Path

import pytest

from cryptobot.data.coin_strategy_repository import CoinStrategyRepository
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.llm.analyzer import ANALYSIS_PROMPT, LLMAnalyzer


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


# ===================================================================
# A. Repository 기본 동작
# ===================================================================


def test_assign_and_get(db):
    repo = CoinStrategyRepository(db)
    ok = repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.7})
    assert ok is True
    a = repo.get_assignment("KRW-BTC")
    assert a["strategy_name"] == "volatility_breakout"
    assert a["params"]["k_value"] == 0.7


def test_get_all_assignments(db):
    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.7})
    repo.assign("KRW-ETH", "ma_crossover", {"short_period": 5})
    all_a = repo.get_all_assignments()
    assert len(all_a) == 2
    assert all_a["KRW-BTC"]["strategy_name"] == "volatility_breakout"


def test_same_strategy_updates_params(db):
    """같은 전략 재배정 시 파라미터만 업데이트 (진동 아님)."""
    repo = CoinStrategyRepository(db, min_hold_minutes=60)
    repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.5})
    ok = repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.8})
    assert ok is True
    a = repo.get_assignment("KRW-BTC")
    assert a["params"]["k_value"] == 0.8


def test_remove(db):
    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "volatility_breakout")
    repo.remove("KRW-BTC")
    assert repo.get_assignment("KRW-BTC") is None


# ===================================================================
# B. 진동 방지 가드
# ===================================================================


def test_different_strategy_within_hold_rejected(db):
    """min_hold_minutes 내 다른 전략 배정 거부."""
    repo = CoinStrategyRepository(db, min_hold_minutes=60)
    repo.assign("KRW-BTC", "volatility_breakout")
    ok = repo.assign("KRW-BTC", "ma_crossover")  # 즉시 전환 시도
    assert ok is False
    # 기존 유지 확인
    a = repo.get_assignment("KRW-BTC")
    assert a["strategy_name"] == "volatility_breakout"


def test_force_overrides_hold_guard(db):
    repo = CoinStrategyRepository(db, min_hold_minutes=60)
    repo.assign("KRW-BTC", "volatility_breakout")
    ok = repo.assign("KRW-BTC", "ma_crossover", force=True)
    assert ok is True
    a = repo.get_assignment("KRW-BTC")
    assert a["strategy_name"] == "ma_crossover"


def test_different_strategy_after_hold_allowed(db):
    """시간 경과 후 재전환 허용."""
    repo = CoinStrategyRepository(db, min_hold_minutes=1)
    repo.assign("KRW-BTC", "volatility_breakout")
    # 2분 전으로 backdate
    db.execute("UPDATE coin_strategy_assignment SET assigned_at = datetime('now', '-2 minutes')")
    db.commit()
    ok = repo.assign("KRW-BTC", "ma_crossover")
    assert ok is True


# ===================================================================
# C. 보유 포지션 중 전략 교체 금지
# ===================================================================


def test_held_coin_strategy_change_deferred(db):
    """보유 중 코인은 전략 변경 거부 (deferred)."""
    recorder = DataRecorder(db)
    recorder.record_trade(
        coin="KRW-BTC",
        side="buy",
        price=100,
        amount=1,
        total_krw=100,
        fee_krw=1,
        strategy="test",
        trigger_reason="test",
    )
    db.commit()

    repo = CoinStrategyRepository(db, min_hold_minutes=0)
    repo.assign("KRW-BTC", "volatility_breakout")

    result = repo.apply_bulk(
        {"KRW-BTC": {"strategy": "ma_crossover", "params": {}}},
        available_strategies={"volatility_breakout", "ma_crossover"},
        held_coins={"KRW-BTC"},
    )
    assert "KRW-BTC" not in result["applied"]
    rej = result["rejected"][0]
    assert rej["reason"] == "held position — deferred"

    # 기존 전략 유지
    a = repo.get_assignment("KRW-BTC")
    assert a["strategy_name"] == "volatility_breakout"


def test_held_coin_same_strategy_allowed(db):
    """보유 중이어도 같은 전략은 params 업데이트 가능."""
    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.5})
    result = repo.apply_bulk(
        {"KRW-BTC": {"strategy": "volatility_breakout", "params": {"k_value": 0.7}}},
        available_strategies={"volatility_breakout"},
        held_coins={"KRW-BTC"},
    )
    assert "KRW-BTC" in result["applied"]
    a = repo.get_assignment("KRW-BTC")
    assert a["params"]["k_value"] == 0.7


# ===================================================================
# D. 유효성 검증
# ===================================================================


def test_apply_bulk_rejects_unknown_strategy(db):
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-BTC": {"strategy": "NONEXISTENT", "params": {}}},
        available_strategies={"volatility_breakout"},
    )
    assert len(result["applied"]) == 0
    assert result["rejected"][0]["reason"] == "unknown strategy"


def test_apply_bulk_rejects_non_dict_spec(db):
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-BTC": "volatility_breakout"},  # 문자열 — dict 아님
        available_strategies={"volatility_breakout"},
    )
    assert result["rejected"][0]["reason"] == "spec is not dict"


def test_apply_bulk_rejects_missing_strategy_field(db):
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-BTC": {"params": {"k_value": 0.7}}},  # strategy 필드 없음
        available_strategies={"volatility_breakout"},
    )
    assert result["rejected"][0]["reason"] == "strategy missing"


def test_apply_bulk_normalizes_coin_prefix(db):
    """'BTC' 입력도 'KRW-BTC'로 정규화."""
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"BTC": {"strategy": "volatility_breakout"}},
        available_strategies={"volatility_breakout"},
    )
    assert "KRW-BTC" in result["applied"]


# ===================================================================
# E. apply_bulk 통합
# ===================================================================


def test_apply_bulk_mixed_valid_invalid(db):
    """유효/무효 혼재 — 유효만 적용, 무효는 rejected."""
    repo = CoinStrategyRepository(db)
    coin_strategies = {
        "KRW-BTC": {"strategy": "volatility_breakout", "params": {"k_value": 0.7}},
        "KRW-ETH": {"strategy": "UNKNOWN", "params": {}},
        "KRW-XRP": {"strategy": "ma_crossover", "params": {}},
        "KRW-BAD": "bad_format",
    }
    result = repo.apply_bulk(
        coin_strategies,
        available_strategies={"volatility_breakout", "ma_crossover"},
    )
    assert set(result["applied"]) == {"KRW-BTC", "KRW-XRP"}
    reasons = {r["coin"]: r["reason"] for r in result["rejected"]}
    assert reasons["KRW-ETH"] == "unknown strategy"
    assert reasons["KRW-BAD"] == "spec is not dict"


# ===================================================================
# F. _apply_recommendations 통합 — coin_strategies 파싱
# ===================================================================


def _seed_strategies(db):
    db.execute("UPDATE strategies SET is_active = 0")
    db.execute("UPDATE strategies SET is_active = 1 WHERE name = 'bb_rsi_combined'")
    db.execute("INSERT INTO llm_decisions (timestamp, model) VALUES (datetime('now'), 'test')")
    db.commit()


def test_apply_recommendations_processes_coin_strategies(db):
    """_apply_recommendations가 coin_strategies dict를 파싱하고 DB에 반영."""
    _seed_strategies(db)
    analyzer = LLMAnalyzer(db)

    result = {
        "market_summary_kr": "test",
        "market_state": "sideways",
        "aggression": 0.5,
        "allow_trading": True,
        "recommended_strategy": "bb_rsi_combined",
        "recommended_params": {},
        "coin_strategies": {
            "KRW-BTC": {"strategy": "volatility_breakout", "params": {"k_value": 0.7}},
            "KRW-ETH": {"strategy": "ma_crossover", "params": {"short_period": 5}},
        },
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)

    row = db.execute(
        "SELECT strategy_name, params_json FROM coin_strategy_assignment WHERE coin = 'KRW-BTC'"
    ).fetchone()
    assert dict(row)["strategy_name"] == "volatility_breakout"
    assert json.loads(dict(row)["params_json"])["k_value"] == 0.7


def test_apply_recommendations_rejects_unknown_coin_strategy(db):
    """coin_strategies에 비존재 전략 → rejected에 기록."""
    _seed_strategies(db)
    analyzer = LLMAnalyzer(db)

    result = {
        "market_summary_kr": "test",
        "market_state": "sideways",
        "aggression": 0.5,
        "allow_trading": True,
        "recommended_strategy": "bb_rsi_combined",
        "recommended_params": {},
        "coin_strategies": {
            "KRW-BTC": {"strategy": "FAKE_STRATEGY", "params": {}},
        },
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)

    assert "_coin_strategies_rejected" in result
    assert result["_coin_strategies_rejected"][0]["coin"] == "KRW-BTC"


def test_apply_recommendations_empty_coin_strategies_no_op(db):
    """빈 coin_strategies는 에러 없이 스킵."""
    _seed_strategies(db)
    analyzer = LLMAnalyzer(db)

    result = {
        "market_summary_kr": "test",
        "market_state": "sideways",
        "aggression": 0.5,
        "allow_trading": True,
        "recommended_strategy": "bb_rsi_combined",
        "recommended_params": {},
        "coin_strategies": {},
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)  # 예외 없어야 함

    rows = db.execute("SELECT * FROM coin_strategy_assignment").fetchall()
    assert len(rows) == 0


# ===================================================================
# G. StrategySelector 통합 — assignment 우선
# ===================================================================


def test_selector_uses_assignment_first(db):
    """get_coin_strategy가 assignment 테이블을 먼저 확인."""
    from unittest.mock import MagicMock

    from cryptobot.bot.strategy_selector import StrategySelector

    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.7})

    config = MagicMock()

    # key별 기본값 시뮬레이션 (StrategySelector._load_strategies가 여러 키 조회)
    def _cfg_get(key, default=None):
        defaults = {
            "stop_loss_pct": "-5.0",
            "trailing_stop_pct": "-3.0",
            "position_size_pct": "100.0",
            "roi_table": "",
            "fallback_strategy": "bb_rsi_combined",
        }
        return defaults.get(key, default if default is not None else "bb_rsi_combined")

    config.get.side_effect = _cfg_get
    sel = StrategySelector(db, config)
    # current_strategy는 bb_rsi_combined인데, BTC는 volatility_breakout 배정됨
    strategy, name = sel.get_coin_strategy("KRW-BTC", "btc", collectors={})
    assert name == "volatility_breakout"
    # 파라미터 오버라이드 확인
    assert strategy.params.extra.get("k_value") == 0.7


def test_selector_falls_back_when_no_assignment(db):
    """assignment 없으면 current_strategy 유지."""
    from unittest.mock import MagicMock

    from cryptobot.bot.strategy_selector import StrategySelector

    config = MagicMock()

    # key별 기본값 시뮬레이션 (StrategySelector._load_strategies가 여러 키 조회)
    def _cfg_get(key, default=None):
        defaults = {
            "stop_loss_pct": "-5.0",
            "trailing_stop_pct": "-3.0",
            "position_size_pct": "100.0",
            "roi_table": "",
            "fallback_strategy": "bb_rsi_combined",
        }
        return defaults.get(key, default if default is not None else "bb_rsi_combined")

    config.get.side_effect = _cfg_get
    sel = StrategySelector(db, config)
    strategy, name = sel.get_coin_strategy("KRW-ETH", "alt", collectors={})
    # 활성 전략(bb_rsi_combined) 또는 폴백
    assert name in {"bb_rsi_combined", "volatility_breakout"}


# ===================================================================
# H. 파라미터 오버라이드 복원
# ===================================================================


def test_strategy_extra_restored_after_override(db):
    """_orig_extra로 복원되는지 — 공유 인스턴스 보호."""
    from unittest.mock import MagicMock

    from cryptobot.bot.strategy_selector import StrategySelector

    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "volatility_breakout", {"k_value": 0.7})

    config = MagicMock()

    # key별 기본값 시뮬레이션 (StrategySelector._load_strategies가 여러 키 조회)
    def _cfg_get(key, default=None):
        defaults = {
            "stop_loss_pct": "-5.0",
            "trailing_stop_pct": "-3.0",
            "position_size_pct": "100.0",
            "roi_table": "",
            "fallback_strategy": "bb_rsi_combined",
        }
        return defaults.get(key, default if default is not None else "bb_rsi_combined")

    config.get.side_effect = _cfg_get
    sel = StrategySelector(db, config)

    strategy, _ = sel.get_coin_strategy("KRW-BTC", "btc", collectors={})
    assert hasattr(strategy, "_orig_extra")
    # main.py의 finally가 복원해야 함 — 직접 시뮬레이션
    strategy.params.extra = strategy._orig_extra
    # 복원 후 k_value가 기본값인지 (volatility_breakout 기본 k_value=0.5)
    assert strategy.params.extra.get("k_value") != 0.7


# ===================================================================
# I. 토큰 비용 시뮬레이션 (회귀 방지용)
# ===================================================================


def test_prompt_size_impact_within_bounds(db):
    """coin_strategies 스펙이 프롬프트에 포함됐지만 크기 과도 증가 없음."""
    # 스펙 추가된 프롬프트 길이
    prompt_chars = len(ANALYSIS_PROMPT)
    # 기본 스펙 추가량: 약 400~600 chars (합리적 범위)
    # ANALYSIS_PROMPT 자체는 템플릿이므로 6000~8000 chars 정도
    assert 5000 < prompt_chars < 10000, f"프롬프트 템플릿 크기 비정상: {prompt_chars}"


# ===================================================================
# J. 프롬프트 스펙 포함 검증
# ===================================================================


def test_prompt_includes_coin_strategies_spec():
    """ANALYSIS_PROMPT에 coin_strategies 스펙이 명시됨."""
    assert "coin_strategies" in ANALYSIS_PROMPT
    assert "코인별로" in ANALYSIS_PROMPT or "코인마다" in ANALYSIS_PROMPT


# ===================================================================
# K. 자동 마이그레이션 — 신규 DB / 기존 DB 모두
# ===================================================================


def test_table_exists_on_fresh_init(db):
    """신규 initialize() 후 coin_strategy_assignment 테이블 존재."""
    row = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coin_strategy_assignment'").fetchone()
    assert row is not None


def test_auto_migration_on_legacy_db():
    """옛 DB(테이블 없음) → initialize() → 자동 생성."""
    tmpdir = tempfile.mkdtemp()
    path = Path(tmpdir) / "legacy.db"
    conn = sqlite3.connect(str(path))
    # 전혀 없는 상태
    conn.close()

    db = Database(path)
    db.initialize()
    try:
        # 테이블 존재 확인
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='coin_strategy_assignment'"
        ).fetchone()
        assert row is not None
        # CRUD 동작 확인
        repo = CoinStrategyRepository(db)
        repo.assign("KRW-BTC", "volatility_breakout")
        assert repo.get_assignment("KRW-BTC") is not None
    finally:
        db.close()
