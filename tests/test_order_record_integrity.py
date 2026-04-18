"""P0 #169 — 주문/기록 무결성 테스트.

검증 대상:
1. _check_and_buy/sell에서 APIError 발생 시 긴급 알림 + record_signal(skip_reason)
2. record_trade 직후 명시적 commit 실행
3. LLM이 미존재 전략 이름 반환 시 기존 전략 유지 + rejected 마킹
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.exceptions import APIError
from cryptobot.llm.analyzer import LLMAnalyzer


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


def test_check_and_buy_api_error_notifies_and_records_signal(db):
    """매수 중 APIError 발생 시: notify_error + record_signal(skip_reason='API 예외: APIError')."""
    from cryptobot.bot.main import CryptoBot

    bot = CryptoBot.__new__(CryptoBot)
    bot._db = db
    bot._recorder = DataRecorder(db)
    bot._notifier = MagicMock()
    bot._trader = MagicMock()
    bot._trader.is_ready = True
    bot._trader.get_balance_krw.return_value = 100_000
    bot._trader.buy_market.side_effect = APIError("Upbit timeout")

    # RiskManager/strategy selector mock
    bot._risk = MagicMock()
    bot._risk.check_can_buy.return_value = (True, "OK")
    bot._risk.limits = MagicMock(min_balance_krw=5000, max_position_size_krw=1_000_000)
    bot._config_mgr = MagicMock()
    bot._config_mgr.get.return_value = "50"
    bot._config_mgr.get_strategy_params_json.return_value = None

    strat = MagicMock()
    strat.check_buy.return_value = MagicMock(
        signal_type="buy",
        confidence=0.8,
        reason="RSI+BB",
        trigger_value=100.0,
    )
    strat.params = MagicMock(position_size_pct=100)
    bot._strategy_sel = MagicMock()
    bot._strategy_sel.current_strategy = strat
    bot._strategy_sel.current_strategy_name = "bb_rsi_combined"

    coll = MagicMock()
    coll.latest_df = pd.DataFrame({"close": [100] * 30})
    bot._coin_mgr = MagicMock(collectors={"KRW-BTC": coll})

    bot._check_and_buy({"market_state": "sideways"}, price=100.0, snapshot_id=None, coin="KRW-BTC")

    bot._notifier.notify_error.assert_called_once()
    # record_signal 중 skip_reason에 "API 예외" 포함 확인
    rows = db.execute("SELECT skip_reason FROM trade_signals ORDER BY id DESC LIMIT 1").fetchall()
    assert len(rows) == 1
    assert "API 예외" in dict(rows[0])["skip_reason"]


def test_check_and_sell_api_error_notifies_and_records_signal(db):
    """매도 중 APIError 발생 시: notify_error + record_signal(skip_reason='API 예외: APIError')."""
    from cryptobot.bot.main import CryptoBot

    bot = CryptoBot.__new__(CryptoBot)
    bot._db = db
    bot._recorder = DataRecorder(db)
    bot._notifier = MagicMock()
    bot._trader = MagicMock()
    bot._trader.is_ready = True
    bot._trader.sell_market.side_effect = APIError("Upbit rate limit")

    bot._config_mgr = MagicMock()
    bot._config_mgr.get_strategy_params_json.return_value = None

    strat = MagicMock()
    strat.check_sell.return_value = MagicMock(
        signal_type="sell",
        confidence=0.7,
        reason="RSI 정상 복귀",
        trigger_value=70.0,
    )
    strat.params = MagicMock()
    strat.params.extra = {}
    strat.params.stop_loss_pct = -5
    strat.params.trailing_stop_pct = -2
    strat._hold_minutes = 10
    bot._strategy_sel = MagicMock()
    bot._strategy_sel.current_strategy = strat
    bot._strategy_sel.current_strategy_name = "bb_rsi_combined"

    coll = MagicMock()
    coll.latest_df = pd.DataFrame({"close": [100] * 30})
    bot._coin_mgr = MagicMock(collectors={"KRW-BTC": coll})

    active_trade = {
        "id": 1,
        "price": 100.0,
        "total_krw": 10000,
        "fee_krw": 5,
        "timestamp": "2026-04-17T00:00:00+00:00",
    }
    bot._check_and_sell(active_trade, price=110.0, snapshot_id=None, coin="KRW-BTC")

    bot._notifier.notify_error.assert_called_once()
    rows = db.execute("SELECT skip_reason FROM trade_signals ORDER BY id DESC LIMIT 1").fetchall()
    assert "API 예외" in dict(rows[0])["skip_reason"]


def test_check_and_buy_commits_immediately_after_record(db):
    """성공 매수 후 명시적 commit이 호출된다 (다음 틱 중복 매수 방지)."""
    from cryptobot.bot.main import CryptoBot
    from cryptobot.bot.trader import OrderResult

    bot = CryptoBot.__new__(CryptoBot)
    bot._db = MagicMock(wraps=db)
    # commit을 명시적으로 spy
    commit_calls = []
    orig_commit = db.commit

    def spy_commit():
        commit_calls.append(1)
        orig_commit()

    bot._db.commit = spy_commit
    # 실제 쿼리는 실제 DB로
    bot._db.execute = db.execute
    bot._recorder = DataRecorder(db)
    bot._notifier = MagicMock()
    bot._trader = MagicMock()
    bot._trader.is_ready = True
    bot._trader.get_balance_krw.return_value = 100_000
    bot._trader.buy_market.return_value = OrderResult(
        success=True,
        side="buy",
        coin="KRW-BTC",
        price=100,
        amount=1,
        total_krw=10_000,
        fee_krw=5,
        order_uuid="test-uuid",
    )
    bot._risk = MagicMock()
    bot._risk.check_can_buy.return_value = (True, "OK")
    bot._risk.limits = MagicMock(min_balance_krw=5000, max_position_size_krw=1_000_000)
    bot._config_mgr = MagicMock()
    bot._config_mgr.get.return_value = "50"
    bot._config_mgr.get_strategy_params_json.return_value = None

    strat = MagicMock()
    strat.check_buy.return_value = MagicMock(
        signal_type="buy",
        confidence=0.8,
        reason="test",
        trigger_value=100.0,
    )
    strat.params = MagicMock(position_size_pct=100)
    strat.params.extra = {"k_value": 0.5}
    strat.params.stop_loss_pct = -5
    strat.params.trailing_stop_pct = -2
    bot._strategy_sel = MagicMock()
    bot._strategy_sel.current_strategy = strat
    bot._strategy_sel.current_strategy_name = "bb_rsi_combined"
    coll = MagicMock()
    coll.latest_df = pd.DataFrame({"close": [100] * 30})
    bot._coin_mgr = MagicMock(collectors={"KRW-BTC": coll})

    bot._check_and_buy({"market_state": "sideways"}, price=100.0, snapshot_id=None, coin="KRW-BTC")

    assert len(commit_calls) >= 1, "매수 후 최소 1회 commit이 호출돼야 함"


def test_rejected_strategy_marks_result_and_preserves_existing(db):
    """LLM이 존재하지 않는 전략 이름 반환 시 기존 전략 유지 + _rejected_strategy 플래그."""
    # available 전략 2개 등록
    # initialize()가 기본 전략을 등록하므로 bb_rsi_combined만 활성화로 세팅
    db.execute("UPDATE strategies SET is_active = 0")
    db.execute("UPDATE strategies SET is_active = 1, is_available = 1 WHERE name = 'bb_rsi_combined'")
    db.execute("INSERT INTO llm_decisions (timestamp, model, output_raw_json) VALUES (datetime('now'), 'test', '{}')")
    db.commit()

    analyzer = LLMAnalyzer(db)
    result = {
        "market_summary_kr": "test",
        "market_state": "sideways",
        "confidence": 0.7,
        "aggression": 0.5,
        "allow_trading": True,
        "should_alert_stop": False,
        "recommended_strategy": "NONEXISTENT_STRATEGY",
        "recommended_params": {},
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)

    # 기존 활성 전략이 유지됨
    active = db.execute("SELECT name FROM strategies WHERE is_active = 1").fetchone()
    assert dict(active)["name"] == "bb_rsi_combined"

    # llm_decisions에 rejected 정보 저장됐는지
    row = db.execute("SELECT input_news_summary FROM llm_decisions ORDER BY id DESC LIMIT 1").fetchone()
    import json as _j

    payload = _j.loads(dict(row)["input_news_summary"])
    assert payload.get("_rejected_strategy") == "NONEXISTENT_STRATEGY"
    assert "사용 가능" in payload.get("_rejected_strategy_reason", "")
