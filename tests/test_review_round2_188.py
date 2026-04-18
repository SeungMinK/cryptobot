"""#188 — 2차 리뷰 후속 수정 테스트.

1. coin_strategy_assignment 파라미터 HARD_LIMITS 클리핑 (CRITICAL)
2. Prompt Caching 실패 시 fallback 재시도 (HIGH)
3. 비활성 전략 assignment 후 fallback 안전성 (MED)
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cryptobot.data.coin_strategy_repository import (
    CoinStrategyRepository,
    _clip_to_hard_limits,
)
from cryptobot.data.database import Database
from cryptobot.llm.analyzer import LLMAnalyzer


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


# ===================================================================
# 1. HARD_LIMITS 클리핑 (CRITICAL)
# ===================================================================


def test_clip_to_hard_limits_clips_bb_std():
    """bb_std=5.0 → 2.5 (HARD_LIMITS 상한)."""
    params = {"bb_std": 5.0, "k_value": 0.5}
    clipped, log = _clip_to_hard_limits(params)
    assert clipped["bb_std"] == 2.5
    assert clipped["k_value"] == 0.5  # 범위 내 → 변화 없음
    assert any(c["field"] == "bb_std" for c in log)


def test_clip_to_hard_limits_clips_rsi_oversold():
    """rsi_oversold=100 → 45 (HARD_LIMITS 상한)."""
    params = {"rsi_oversold": 100}
    clipped, log = _clip_to_hard_limits(params)
    assert clipped["rsi_oversold"] == 45


def test_clip_to_hard_limits_ignores_unknown_keys():
    """HARD_LIMITS에 없는 키는 그대로."""
    params = {"custom_param": 9999}
    clipped, log = _clip_to_hard_limits(params)
    assert clipped["custom_param"] == 9999
    assert not log


def test_clip_to_hard_limits_handles_non_numeric():
    """숫자 캐스팅 실패하는 값은 그대로 (에러 없음)."""
    params = {"k_value": "not_a_number"}
    clipped, log = _clip_to_hard_limits(params)
    assert clipped["k_value"] == "not_a_number"


def test_assign_clips_invalid_params(db):
    """CoinStrategyRepository.assign이 범위 밖 값을 자동 클리핑."""
    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "bb_rsi_combined", {"bb_std": 5.0, "rsi_oversold": 100})

    a = repo.get_assignment("KRW-BTC")
    # 클리핑된 값이 저장됨
    assert a["params"]["bb_std"] == 2.5
    assert a["params"]["rsi_oversold"] == 45


def test_apply_bulk_clips_before_storing(db):
    """apply_bulk도 assign을 거치므로 클리핑 적용됨."""
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-BTC": {"strategy": "bb_rsi_combined", "params": {"bb_std": 10.0}}},
        available_strategies={"bb_rsi_combined"},
    )
    assert "KRW-BTC" in result["applied"]
    a = repo.get_assignment("KRW-BTC")
    assert a["params"]["bb_std"] == 2.5  # 클리핑됨


# ===================================================================
# 2. Prompt Caching fallback (HIGH)
# ===================================================================


def test_call_claude_falls_back_when_cache_rejected(db, monkeypatch):
    """cache_control 관련 에러 시 system 평문으로 재시도."""
    a = LLMAnalyzer(db)
    a._api_key = "sk-test"

    call_log = []

    class _FakeClient:
        def __init__(self, api_key):
            pass

        @property
        def messages(self):
            return self

        def create(self, **kwargs):
            call_log.append(kwargs)
            # 첫 호출(캐시 포함): cache 에러 모사
            if isinstance(kwargs.get("system"), list):
                raise Exception("Invalid cache_control parameter")
            # 두번째(평문): 정상 응답
            usage = SimpleNamespace(input_tokens=100, output_tokens=50)
            content_block = SimpleNamespace(
                text='{"market_summary_kr":"t","market_state":"sideways","confidence":0.5,'
                '"aggression":0.5,"should_alert_stop":false,"allow_trading":true,'
                '"recommended_strategy":"bb_rsi_combined","recommended_params":{},'
                '"reasoning":"t"}'
            )
            return SimpleNamespace(usage=usage, content=[content_block])

    monkeypatch.setattr("anthropic.Anthropic", _FakeClient)
    result = a._call_claude("prompt")

    # 재시도로 성공
    assert result is not None
    # 1회는 list(cache 포함), 1회는 평문 — 총 2회 호출
    assert len(call_log) == 2
    assert isinstance(call_log[0]["system"], list)
    assert isinstance(call_log[1]["system"], str)


def test_call_claude_non_cache_error_does_not_trigger_fallback(db, monkeypatch):
    """캐시와 무관한 에러(예: 네트워크)는 fallback 유도하지 않음."""
    a = LLMAnalyzer(db)
    a._api_key = "sk-test"

    call_log = []

    class _FakeClient:
        def __init__(self, api_key):
            pass

        @property
        def messages(self):
            return self

        def create(self, **kwargs):
            call_log.append(kwargs)
            # 모든 호출 네트워크 에러
            raise Exception("Connection timeout")

    monkeypatch.setattr("anthropic.Anthropic", _FakeClient)
    result = a._call_claude("prompt")
    # 전부 실패하면 None — fallback이 아닌 재시도
    assert result is None
    # 모든 호출이 여전히 list system (fallback 안 됨)
    for c in call_log:
        assert isinstance(c["system"], list)


# ===================================================================
# 3. 비활성 전략 fallback (MED)
# ===================================================================


def test_disabled_strategy_in_assignment_falls_back_to_current(db):
    """assignment에 있는 전략이 is_available=FALSE로 바뀐 경우 fallback 동작."""
    from cryptobot.bot.strategy_selector import StrategySelector

    # 특정 전략을 비활성으로 만듦 (coin에 배정된 상태)
    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "ma_crossover", {"short_period": 5})

    # 이제 ma_crossover를 is_available=FALSE로 전환
    db.execute("UPDATE strategies SET is_available = 0 WHERE name = 'ma_crossover'")
    db.execute("UPDATE strategies SET is_active = 1 WHERE name = 'bb_rsi_combined'")
    db.commit()

    config = MagicMock()

    def _cfg(key, default=None):
        defaults = {
            "stop_loss_pct": "-5.0",
            "trailing_stop_pct": "-3.0",
            "position_size_pct": "100.0",
            "roi_table": "",
            "fallback_strategy": "bb_rsi_combined",
        }
        return defaults.get(key, default if default is not None else "bb_rsi_combined")

    config.get.side_effect = _cfg

    sel = StrategySelector(db, config)
    # ma_crossover는 비활성 → 레지스트리에 없어 None 반환 → fallback 체인 타야 함
    strategy, name = sel.get_coin_strategy("KRW-BTC", "btc", collectors={})
    # 크래시 없이 어떤 전략이든 돌려받기
    assert strategy is not None
    # 비활성 전략이 아닌 다른 전략 (current_strategy or fallback)이 반환됨
    assert name != "ma_crossover"
