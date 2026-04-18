"""계좌 전체 일일 실현 손실 가드 테스트.

- 매수는 차단하되 매도는 영향 없음 확인
- 흑자/손익 근사치 계산 정확성
"""

import tempfile
from pathlib import Path

import pytest

from cryptobot.bot.risk import RiskLimits, RiskManager
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    yield db
    db.close()


def _record_sell_loss(db, coin: str, loss_krw: float) -> None:
    """매수 + 손실 매도 기록 (오늘 KST 시각으로)."""
    rec = DataRecorder(db)
    buy_id = rec.record_trade(
        coin=coin,
        side="buy",
        price=100,
        amount=1,
        total_krw=100_000,
        fee_krw=50,
        strategy="test",
        trigger_reason="test",
    )
    rec.record_trade(
        coin=coin,
        side="sell",
        price=95,
        amount=1,
        total_krw=95_000,
        fee_krw=48,
        strategy="test",
        trigger_reason="손절",
        buy_trade_id=buy_id,
        profit_pct=-5.0,
        profit_krw=loss_krw,
    )


# ===================================================================
# 1. 계좌 일일 손실 한도 — 기본 동작
# ===================================================================


def test_account_loss_allows_when_no_losses(db):
    """손실 없으면 매수 허용."""
    rm = RiskManager(db, RiskLimits(max_daily_account_loss_pct=-10.0))
    ok, reason = rm.check_account_daily_loss(current_krw=1_000_000)
    assert ok is True


def test_account_loss_allows_when_within_limit(db):
    """계좌 손실이 한도 안이면 허용."""
    _record_sell_loss(db, "KRW-BTC", loss_krw=-50_000)  # -5%
    rm = RiskManager(db, RiskLimits(max_daily_account_loss_pct=-10.0))
    # 현재 KRW = 950,000, 실현 -50,000 → 시작 자산 = 1,000,000 → 손실 -5%
    ok, reason = rm.check_account_daily_loss(current_krw=950_000)
    assert ok is True


def test_account_loss_blocks_when_limit_reached(db):
    """한도 초과 시 매수 차단."""
    _record_sell_loss(db, "KRW-BTC", loss_krw=-120_000)  # -12%
    rm = RiskManager(db, RiskLimits(max_daily_account_loss_pct=-10.0))
    # 시작 자산 = 880,000 + 0 + 120,000 = 1,000,000 → 손실 -12%
    ok, reason = rm.check_account_daily_loss(current_krw=880_000)
    assert ok is False
    assert "계좌 일일 손실 한도" in reason


def test_account_loss_uses_held_cost_in_start_asset(db):
    """보유 포지션 원가도 시작 자산에 포함."""
    rec = DataRecorder(db)
    # 매도 없이 보유 중인 코인 (매수 원가 500,000)
    rec.record_trade(
        coin="KRW-ETH",
        side="buy",
        price=100,
        amount=1,
        total_krw=500_000,
        fee_krw=250,
        strategy="test",
        trigger_reason="test",
    )
    # 오늘 다른 코인에서 -80,000 손실 (다른 buy + sell)
    _record_sell_loss(db, "KRW-BTC", loss_krw=-80_000)

    rm = RiskManager(db, RiskLimits(max_daily_account_loss_pct=-10.0))
    # 현재 KRW = 420,000, 보유 원가 = 500,000, 실현 -80,000
    # 시작 자산 = 420,000 + 500,000 + 80,000 = 1,000,000 → 손실 -8% → 통과
    ok, reason = rm.check_account_daily_loss(current_krw=420_000)
    assert ok is True


def test_account_loss_gate_does_not_affect_sell(db):
    """check_can_sell은 항상 True — 계좌 손실 가드 무관."""
    _record_sell_loss(db, "KRW-BTC", loss_krw=-200_000)  # -20%
    rm = RiskManager(db, RiskLimits(max_daily_account_loss_pct=-10.0))
    # 매수는 차단
    ok_buy, _ = rm.check_account_daily_loss(current_krw=800_000)
    assert ok_buy is False
    # 매도는 여전히 허용
    ok_sell, _ = rm.check_can_sell("KRW-BTC")
    assert ok_sell is True


# ===================================================================
# 2. 엣지 케이스
# ===================================================================


def test_account_loss_zero_start_asset_safe(db):
    """시작 자산이 0이거나 음수면 (비정상) True 반환 (차단 안 함)."""
    rm = RiskManager(db, RiskLimits())
    ok, _ = rm.check_account_daily_loss(current_krw=0)
    assert ok is True  # 0이면 계산 불가 → 통과


def test_account_loss_multi_sells(db):
    """같은 날 여러 매도 합계가 누적 계산됨."""
    _record_sell_loss(db, "KRW-BTC", loss_krw=-60_000)
    _record_sell_loss(db, "KRW-ETH", loss_krw=-50_000)
    # 합계 -110,000 → 시작 자산 1,000,000 가정 → -11% → 차단
    rm = RiskManager(db, RiskLimits(max_daily_account_loss_pct=-10.0))
    ok, _ = rm.check_account_daily_loss(current_krw=890_000)
    assert ok is False


# ===================================================================
# 3. 새 리스크 한도값
# ===================================================================


def test_new_risk_limits_defaults():
    """#account-guard PR에서 기본값 조정."""
    limits = RiskLimits()
    assert limits.max_daily_loss_pct == -7.0  # 기존 -10 → -7
    assert limits.max_consecutive_losses == 3  # 기존 5 → 3
    assert limits.max_position_size_krw == 300_000  # 기존 1,000,000 → 300,000
    assert limits.max_daily_account_loss_pct == -10.0  # 신규
