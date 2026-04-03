"""데이터 기록 모듈 테스트."""

import tempfile
from pathlib import Path

from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder


def _make_recorder():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    return DataRecorder(db), db


def test_record_and_get_signal():
    """신호 기록 및 조회."""
    recorder, db = _make_recorder()
    try:
        signal_id = recorder.record_signal(
            coin="KRW-BTC",
            signal_type="buy_signal",
            strategy="volatility_breakout",
            confidence=0.8,
            trigger_reason="변동성 돌파",
            current_price=50000000,
        )
        assert signal_id is not None
        assert signal_id > 0
    finally:
        db.close()


def test_record_trade_and_get_active():
    """매매 기록 후 활성 매수 조회."""
    recorder, db = _make_recorder()
    try:
        trade_id = recorder.record_trade(
            coin="KRW-BTC",
            side="buy",
            price=50000000,
            amount=0.001,
            total_krw=50000,
            fee_krw=25,
            strategy="volatility_breakout",
            trigger_reason="변동성 돌파",
        )
        assert trade_id is not None

        active = recorder.get_active_buy_trade("KRW-BTC")
        assert active is not None
        assert active["price"] == 50000000
    finally:
        db.close()


def test_no_active_after_sell():
    """매도 후 활성 매수 없음."""
    recorder, db = _make_recorder()
    try:
        buy_id = recorder.record_trade(
            coin="KRW-BTC",
            side="buy",
            price=50000000,
            amount=0.001,
            total_krw=50000,
            fee_krw=25,
            strategy="volatility_breakout",
            trigger_reason="변동성 돌파",
        )
        recorder.record_trade(
            coin="KRW-BTC",
            side="sell",
            price=51000000,
            amount=0.001,
            total_krw=51000,
            fee_krw=25.5,
            strategy="volatility_breakout",
            trigger_reason="트레일링 스탑",
            buy_trade_id=buy_id,
            profit_pct=2.0,
            profit_krw=1000,
        )

        active = recorder.get_active_buy_trade("KRW-BTC")
        assert active is None
    finally:
        db.close()
