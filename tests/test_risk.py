"""리스크 관리 테스트."""

import tempfile
from pathlib import Path

from cryptobot.bot.risk import RiskLimits, RiskManager
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder


def _make_risk_manager(limits: RiskLimits | None = None):
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    return RiskManager(db, limits), DataRecorder(db), db


def test_can_buy_normal():
    """정상 상황에서 매수 허용."""
    rm, _, db = _make_risk_manager()
    try:
        can, reason = rm.check_can_buy("KRW-BTC", 100_000, 500_000)
        assert can is True
    finally:
        db.close()


def test_block_min_balance():
    """최소 잔고 미달 시 차단."""
    limits = RiskLimits(min_balance_krw=50_000)
    rm, _, db = _make_risk_manager(limits)
    try:
        can, reason = rm.check_can_buy("KRW-BTC", 80_000, 100_000)
        assert can is False
        assert "최소 잔고" in reason
    finally:
        db.close()


def test_block_max_position_size():
    """최대 매수 금액 초과 시 차단."""
    limits = RiskLimits(max_position_size_krw=100_000)
    rm, _, db = _make_risk_manager(limits)
    try:
        can, reason = rm.check_can_buy("KRW-BTC", 200_000, 500_000)
        assert can is False
        assert "최대 매수 금액" in reason
    finally:
        db.close()


def test_block_daily_trades_limit():
    """일일 거래 횟수 초과 시 차단."""
    limits = RiskLimits(max_daily_trades=2)
    rm, recorder, db = _make_risk_manager(limits)
    try:
        # 2건 거래 기록
        for _ in range(2):
            recorder.record_trade(
                coin="KRW-BTC",
                side="buy",
                price=50000000,
                amount=0.001,
                total_krw=50000,
                fee_krw=25,
                strategy="test",
                trigger_reason="test",
            )

        can, reason = rm.check_can_buy("KRW-BTC", 50_000, 500_000)
        assert can is False
        assert "거래 횟수" in reason
    finally:
        db.close()


def test_block_consecutive_losses():
    """연속 손실 시 차단."""
    limits = RiskLimits(max_consecutive_losses=2)
    rm, recorder, db = _make_risk_manager(limits)
    try:
        for i in range(2):
            buy_id = recorder.record_trade(
                coin="KRW-BTC",
                side="buy",
                price=50000000,
                amount=0.001,
                total_krw=50000,
                fee_krw=25,
                strategy="test",
                trigger_reason="test",
            )
            recorder.record_trade(
                coin="KRW-BTC",
                side="sell",
                price=49000000,
                amount=0.001,
                total_krw=49000,
                fee_krw=24.5,
                strategy="test",
                trigger_reason="손절",
                buy_trade_id=buy_id,
                profit_pct=-2.0,
                profit_krw=-1000,
            )

        can, reason = rm.check_can_buy("KRW-BTC", 50_000, 500_000)
        assert can is False
        assert "연속" in reason
    finally:
        db.close()


def test_safe_position_size():
    """안전한 매수 금액 계산 (기본: confidence=1.0, position_size_pct=100)."""
    limits = RiskLimits(min_balance_krw=10_000, max_position_size_krw=500_000)
    rm, _, db = _make_risk_manager(limits)
    try:
        # 잔고 100,000 - 최소잔고 10,000 = 90,000
        size = rm.get_safe_position_size(100_000)
        assert size == 90_000

        # 잔고 1,000,000 - 최소잔고 10,000 = 990,000 → max 500,000으로 제한
        size = rm.get_safe_position_size(1_000_000)
        assert size == 500_000

        # 잔고 부족
        size = rm.get_safe_position_size(5_000)
        assert size == 0
    finally:
        db.close()


def test_position_size_with_confidence():
    """confidence에 비례하여 매수 금액이 조절된다."""
    limits = RiskLimits(min_balance_krw=10_000, max_position_size_krw=1_000_000)
    rm, _, db = _make_risk_manager(limits)
    try:
        # 잔고 110,000 → 가용 100,000
        # confidence=0.5 → 50,000
        size = rm.get_safe_position_size(110_000, confidence=0.5)
        assert size == 50_000

        # confidence=0.3 → 30,000
        size = rm.get_safe_position_size(110_000, confidence=0.3)
        assert size == 30_000

        # confidence=1.0 → 100,000 (전액)
        size = rm.get_safe_position_size(110_000, confidence=1.0)
        assert size == 100_000

        # confidence=0.0 → 0
        size = rm.get_safe_position_size(110_000, confidence=0.0)
        assert size == 0
    finally:
        db.close()


def test_position_size_with_pct():
    """position_size_pct로 최대 비율을 제한한다."""
    limits = RiskLimits(min_balance_krw=10_000, max_position_size_krw=1_000_000)
    rm, _, db = _make_risk_manager(limits)
    try:
        # 가용 100,000, confidence=1.0, pct=50 → 50,000
        size = rm.get_safe_position_size(110_000, confidence=1.0, position_size_pct=50.0)
        assert size == 50_000

        # 가용 100,000, confidence=0.7, pct=50 → 35,000
        size = rm.get_safe_position_size(110_000, confidence=0.7, position_size_pct=50.0)
        assert size == 35_000
    finally:
        db.close()


def test_position_size_capped_by_max():
    """confidence×pct 적용 후에도 max_position_size_krw로 상한 제한."""
    limits = RiskLimits(min_balance_krw=10_000, max_position_size_krw=50_000)
    rm, _, db = _make_risk_manager(limits)
    try:
        # 가용 990,000, confidence=1.0 → 990,000이지만 max 50,000
        size = rm.get_safe_position_size(1_000_000, confidence=1.0)
        assert size == 50_000
    finally:
        db.close()


def test_min_order_amount_check():
    """업비트 최소 주문 금액(5,000원) 미달 시 차단."""
    rm, _, db = _make_risk_manager()
    try:
        can, reason = rm.check_can_buy("KRW-BTC", 3_000, 500_000)
        assert can is False
        assert "최소 주문 금액" in reason
    finally:
        db.close()


def test_sell_always_allowed():
    """매도는 항상 허용 (손절 차단하면 안 됨)."""
    rm, _, db = _make_risk_manager()
    try:
        can, _ = rm.check_can_sell("KRW-BTC")
        assert can is True
    finally:
        db.close()
