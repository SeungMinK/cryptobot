"""P3 #172 — 미테스트 코어 경로 커버.

High:
- order_uuid end-to-end (buy → record_trade에 uuid 저장)
- duplicate buy 방지 (get_active_buy_trade)

Medium:
- _apply_recommendations: bot_config/strategy 업데이트 반영
- _save_decision 비용 계산 정확성

Low:
- check_emergency 전용 (held/non_held 임계치 적용)
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.llm.analyzer import LLMAnalyzer
from cryptobot.strategies.base import Signal


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


# ===================================================================
# order_uuid end-to-end
# ===================================================================


def test_order_uuid_persisted_to_trades(db):
    """매수 실행 후 order.order_uuid가 trades.order_uuid 컬럼에 저장된다."""
    from cryptobot.bot.main import CryptoBot
    from cryptobot.bot.trader import OrderResult

    bot = CryptoBot.__new__(CryptoBot)
    bot._db = db
    bot._recorder = DataRecorder(db)
    bot._notifier = MagicMock()
    bot._trader = MagicMock()
    bot._trader.is_ready = True
    bot._trader.get_balance_krw.return_value = 100_000
    bot._trader.buy_market.return_value = OrderResult(
        success=True, side="buy", coin="KRW-BTC", price=100, amount=1,
        total_krw=10_000, fee_krw=5, order_uuid="unique-order-abc123",
    )
    bot._risk = MagicMock()
    bot._risk.check_can_buy.return_value = (True, "OK")
    bot._risk.limits = MagicMock(min_balance_krw=5000, max_position_size_krw=1_000_000)
    bot._config_mgr = MagicMock()
    bot._config_mgr.get.return_value = "50"
    bot._config_mgr.get_strategy_params_json.return_value = None

    strat = MagicMock()
    strat.check_buy.return_value = Signal("buy", 0.8, "test")
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

    row = db.execute(
        "SELECT order_uuid FROM trades WHERE coin = 'KRW-BTC' AND side = 'buy'"
    ).fetchone()
    assert dict(row)["order_uuid"] == "unique-order-abc123"


# ===================================================================
# duplicate buy 방지
# ===================================================================


def test_duplicate_buy_blocked_when_active_position_exists(db):
    """get_active_buy_trade()가 기존 매수를 찾으면 새 매수 실행 안 됨."""
    from cryptobot.bot.main import CryptoBot
    from cryptobot.bot.trader import OrderResult

    recorder = DataRecorder(db)
    # 기존 open 포지션
    recorder.record_trade(
        coin="KRW-BTC", side="buy", price=100, amount=1, total_krw=100, fee_krw=1,
        strategy="test", trigger_reason="test",
    )
    db.commit()

    bot = CryptoBot.__new__(CryptoBot)
    bot._db = db
    bot._recorder = recorder
    bot._notifier = MagicMock()
    bot._trader = MagicMock()
    bot._trader.is_ready = True
    bot._trader.get_balance_krw.return_value = 100_000
    bot._trader.buy_market.return_value = OrderResult(
        success=True, side="buy", coin="KRW-BTC", price=100, amount=1,
        total_krw=10_000, fee_krw=5, order_uuid="new-order",
    )
    bot._risk = MagicMock()
    bot._risk.check_can_buy.return_value = (True, "OK")
    bot._risk.limits = MagicMock(min_balance_krw=5000, max_position_size_krw=1_000_000)
    bot._config_mgr = MagicMock()
    bot._config_mgr.get.return_value = "50"
    bot._config_mgr.get_strategy_params_json.return_value = None

    strat = MagicMock()
    strat.check_buy.return_value = Signal("buy", 0.8, "test")
    strat.params = MagicMock(position_size_pct=100)
    bot._strategy_sel = MagicMock()
    bot._strategy_sel.current_strategy = strat
    bot._strategy_sel.current_strategy_name = "bb_rsi_combined"
    coll = MagicMock()
    coll.latest_df = pd.DataFrame({"close": [100] * 30})
    bot._coin_mgr = MagicMock(collectors={"KRW-BTC": coll})

    bot._check_and_buy({"market_state": "sideways"}, price=100.0, snapshot_id=None, coin="KRW-BTC")

    # 신규 주문 실행 안 됨
    bot._trader.buy_market.assert_not_called()


# ===================================================================
# _apply_recommendations
# ===================================================================


def test_apply_recommendations_updates_bot_config(db):
    """LLM 추천값이 bot_config에 UPDATE로 반영된다."""
    analyzer = LLMAnalyzer(db)
    # 사전 값
    db.execute(
        "INSERT OR REPLACE INTO bot_config (key, value, display_name) "
        "VALUES ('stop_loss_pct', '-5', 'SL')"
    )
    db.execute("UPDATE strategies SET is_active = 0")
    db.execute("UPDATE strategies SET is_active = 1 WHERE name = 'bb_rsi_combined'")
    db.execute(
        "INSERT INTO llm_decisions (timestamp, model) VALUES (datetime('now'), 'test')"
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
        "recommended_params": {
            "stop_loss_pct": -8.0,
            "trailing_stop_pct": -4.0,
        },
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)

    # bot_config 반영 확인
    row = db.execute("SELECT value FROM bot_config WHERE key = 'stop_loss_pct'").fetchone()
    assert float(dict(row)["value"]) == -8.0


def test_apply_recommendations_merges_strategy_params(db):
    """LLM 전략별 파라미터가 strategies.default_params_json에 머지된다."""
    analyzer = LLMAnalyzer(db)
    import json as _j
    db.execute(
        "UPDATE strategies SET default_params_json = ? WHERE name = 'bb_rsi_combined'",
        (_j.dumps({"rsi_oversold": 30, "bb_std": 2.0, "bb_period": 20}),),
    )
    db.execute("UPDATE strategies SET is_active = 0")
    db.execute("UPDATE strategies SET is_active = 1 WHERE name = 'bb_rsi_combined'")
    db.execute(
        "INSERT INTO llm_decisions (timestamp, model) VALUES (datetime('now'), 'test')"
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
        "recommended_params": {
            "rsi_oversold": 25,
            "bb_std": 1.5,
            # bb_period는 안 건드림 → 유지돼야 함
        },
        "reasoning": "test",
    }
    analyzer._apply_recommendations(result)

    row = db.execute(
        "SELECT default_params_json FROM strategies WHERE name = 'bb_rsi_combined'"
    ).fetchone()
    merged = _j.loads(dict(row)["default_params_json"])
    assert merged["rsi_oversold"] == 25  # 업데이트
    assert merged["bb_std"] == 1.5  # 업데이트
    assert merged["bb_period"] == 20  # 기존 유지


# ===================================================================
# _save_decision 비용 계산
# ===================================================================


def test_save_decision_cost_calculation(db):
    """Haiku 4.5 공식가로 cost_usd 저장."""
    analyzer = LLMAnalyzer(db)
    result = {
        "market_summary_kr": "test",
        "reasoning": "test",
        "market_state": "sideways",
        "aggression": 0.5,
        "allow_trading": True,
        "recommended_params": {},
        "_input_tokens": 100_000,  # 10만 input
        "_output_tokens": 5_000,  # 5천 output
    }
    analyzer._save_decision(result)
    # 100000/1M * $1 + 5000/1M * $5 = 0.1 + 0.025 = $0.125
    row = db.execute(
        "SELECT cost_usd, input_tokens, output_tokens FROM llm_decisions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    d = dict(row)
    assert d["input_tokens"] == 100_000
    assert d["output_tokens"] == 5_000
    assert abs(d["cost_usd"] - 0.125) < 1e-5


# ===================================================================
# check_emergency
# ===================================================================


def test_check_emergency_held_vs_non_held_thresholds(db):
    """보유 코인은 낮은 임계치, 비보유는 높은 임계치로 급변 감지."""
    analyzer = LLMAnalyzer(db)
    # 보유 코인 등록
    recorder = DataRecorder(db)
    recorder.record_trade(
        coin="KRW-BTC", side="buy", price=100, amount=1, total_krw=100, fee_krw=1,
        strategy="test", trigger_reason="test",
    )
    db.commit()

    # market_snapshots 2개 세팅: BTC(보유) +4%, ETH(비보유) +4%
    # held_threshold=3.0, non_held=7.0 → BTC는 트리거, ETH는 트리거 안 됨
    db.execute(
        "INSERT INTO market_snapshots (coin, timestamp, price) "
        "VALUES ('KRW-BTC', datetime('now', '-65 minutes'), 100)"
    )
    db.execute(
        "INSERT INTO market_snapshots (coin, timestamp, price) "
        "VALUES ('KRW-BTC', datetime('now'), 104)"  # +4%
    )
    db.execute(
        "INSERT INTO market_snapshots (coin, timestamp, price) "
        "VALUES ('KRW-ETH', datetime('now', '-65 minutes'), 100)"
    )
    db.execute(
        "INSERT INTO market_snapshots (coin, timestamp, price) "
        "VALUES ('KRW-ETH', datetime('now'), 104)"  # +4%
    )
    db.commit()

    # BTC +4% > held_th(3.0) → emergency 감지
    emergency = analyzer.check_emergency()
    assert emergency is True

    # BTC가 없다면? 비보유 ETH +4% < non_held_th(7.0) → 감지 안 됨
    db.execute("DELETE FROM market_snapshots WHERE coin = 'KRW-BTC'")
    db.execute("DELETE FROM trades")  # 보유 코인도 제거
    db.commit()
    assert analyzer.check_emergency() is False
