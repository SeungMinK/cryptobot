"""#186 — #152 #183 리뷰 후속 수정 테스트.

1. _orig_extra 예외 경로 안전 복원
2. SDK usage 파싱 실패 시 크래시 없음
3. 모니터링 외 코인 배정 거부
4. SYSTEM_PROMPT 예시 JSON 전략 파라미터 언급
5. _orig_extra 빈 assignment_params여도 일관된 동작
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from cryptobot.data.coin_strategy_repository import CoinStrategyRepository
from cryptobot.data.database import Database
from cryptobot.llm.analyzer import SYSTEM_PROMPT, LLMAnalyzer


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


# ===================================================================
# 1. _orig_extra 복원 안전성 — main.py finally
# ===================================================================


def test_orig_extra_finally_restores_even_after_exception():
    """finally 복원 로직 자체 검증 — 공유 인스턴스 강건성.

    main._tick_coin의 finally 로직을 재현:
    - 예외 발생 상황에서도 _orig_extra가 항상 복원되고 제거된다.
    """

    # main.py의 finally 블록과 동일한 로직 시뮬레이션
    class _Params:
        extra: dict

    class _Strat:
        params = _Params()

    strat = _Strat()
    strat.params.extra = {"k_value": 0.99}  # 오버라이드된 상태
    strat._orig_extra = {"k_value": 0.5}  # 원본

    # finally 코드를 직접 실행 (예외 경로 모사)
    try:
        raise RuntimeError("forced exception in tick")
    except RuntimeError:
        pass
    finally:
        if hasattr(strat, "_orig_extra"):
            try:
                strat.params.extra = strat._orig_extra
            finally:
                try:
                    delattr(strat, "_orig_extra")
                except AttributeError:
                    pass

    # 복원 + 정리 확인
    assert not hasattr(strat, "_orig_extra"), "_orig_extra 정리 실패"
    assert strat.params.extra == {"k_value": 0.5}, "원본 복원 실패"


def test_orig_extra_restore_survives_restore_exception():
    """복원 중 예외가 나도 marker는 제거된다 (오염 방지)."""

    class _Strat:
        pass

    strat = _Strat()
    strat._orig_extra = {"k_value": 0.5}

    # 복원 중 예외 — params가 없는 경우 모사
    try:
        if hasattr(strat, "_orig_extra"):
            try:
                strat.params.extra = strat._orig_extra  # AttributeError (params 없음)
            finally:
                try:
                    delattr(strat, "_orig_extra")
                except AttributeError:
                    pass
    except AttributeError:
        pass  # params 없어 에러 나도 marker는 정리됨

    assert not hasattr(strat, "_orig_extra"), "예외 중에도 marker 정리돼야 함"


# ===================================================================
# 2. SDK usage 파싱 실패 시 크래시 없음
# ===================================================================


def test_call_claude_survives_missing_usage(db, monkeypatch):
    """response.usage 자체가 없어도 응답 처리는 계속."""
    a = LLMAnalyzer(db)
    a._api_key = "sk-test"

    class _FakeClient:
        def __init__(self, api_key):
            pass

        @property
        def messages(self):
            return self

        def create(self, **kwargs):
            # usage 없는 응답
            content_block = SimpleNamespace(
                text='{"market_summary_kr":"t","market_state":"sideways",'
                '"confidence":0.5,"aggression":0.5,"should_alert_stop":false,'
                '"allow_trading":true,"recommended_strategy":"bb_rsi_combined",'
                '"recommended_params":{},"reasoning":"t"}'
            )
            # usage 속성 자체 없음
            resp = SimpleNamespace(content=[content_block])
            return resp

    monkeypatch.setattr("anthropic.Anthropic", _FakeClient)
    result = a._call_claude("prompt")
    # 크래시 없이 결과 반환
    assert result is not None
    assert result["_input_tokens"] == 0
    assert result["_output_tokens"] == 0


# ===================================================================
# 3. 모니터링 외 코인 배정 거부
# ===================================================================


def test_apply_bulk_rejects_coin_not_in_active(db):
    """active_coins에 없는 코인은 rejected."""
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-UNKNOWN": {"strategy": "volatility_breakout"}},
        available_strategies={"volatility_breakout"},
        active_coins={"KRW-BTC"},  # UNKNOWN은 여기 없음
    )
    assert not result["applied"]
    assert result["rejected"][0]["reason"] == "coin not monitored"


def test_apply_bulk_accepts_coin_in_active(db):
    """active_coins에 있는 코인은 정상 배정."""
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-BTC": {"strategy": "volatility_breakout"}},
        available_strategies={"volatility_breakout"},
        active_coins={"KRW-BTC"},
    )
    assert "KRW-BTC" in result["applied"]


def test_apply_bulk_active_coins_none_skips_check(db):
    """active_coins=None이면 모니터링 필터 스킵 (기존 동작 호환)."""
    repo = CoinStrategyRepository(db)
    result = repo.apply_bulk(
        {"KRW-NEW": {"strategy": "volatility_breakout"}},
        available_strategies={"volatility_breakout"},
        active_coins=None,
    )
    assert "KRW-NEW" in result["applied"]


# ===================================================================
# 4. SYSTEM_PROMPT 예시 JSON 완전성
# ===================================================================


def test_system_prompt_example_includes_strategy_specific_params():
    """예시 JSON에 bb_rsi_combined 등 전략 파라미터 언급."""
    # 최소 rsi_oversold와 bb_std가 예시나 부연 설명에 있어야 LLM이 포함할 확률↑
    assert "rsi_oversold" in SYSTEM_PROMPT
    assert "bb_std" in SYSTEM_PROMPT
    # 전략별 파라미터 매핑 표도 있어야 함
    assert "volatility_breakout: k_value" in SYSTEM_PROMPT


# ===================================================================
# 5. _orig_extra 일관성 — assignment_params=None vs {}
# ===================================================================


def test_selector_sets_orig_extra_when_assignment_empty_params(db):
    """assignment가 있지만 params_json이 빈 dict여도 _orig_extra 설정."""
    from cryptobot.bot.strategy_selector import StrategySelector

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

    # 빈 params_json으로 assignment 생성
    repo = CoinStrategyRepository(db)
    repo.assign("KRW-BTC", "volatility_breakout", params={})  # params 빈 dict

    sel = StrategySelector(db, config)
    strategy, _ = sel.get_coin_strategy("KRW-BTC", "btc", collectors={})

    # 빈 params여도 _orig_extra 설정 (복원 일관성)
    assert hasattr(strategy, "_orig_extra"), "params 빈 dict여도 _orig_extra 설정해야 함"
