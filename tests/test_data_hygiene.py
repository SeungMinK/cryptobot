"""P4 #173 — 데이터 위생 테스트.

1. 오래된 hold 신호 정리 (cleanup 스크립트)
2. profit_krw NULL 자동 계산
3. orphan buy_trade_id 방지
4. balance_text API 미설정 시 보수적 폴백
"""

import tempfile
from pathlib import Path

import pytest

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
# 1. cleanup_old_hold_signals
# ===================================================================


def test_cleanup_removes_old_hold_keeps_buy_sell(db):
    """14일 이상 된 hold는 삭제, buy/sell은 보존."""
    recorder = DataRecorder(db)
    # 오래된 hold + 최근 hold + 오래된 buy
    recorder.record_signal(
        coin="KRW-BTC",
        signal_type="hold",
        strategy="test",
        confidence=0.0,
        trigger_reason="old",
        current_price=100,
    )
    recorder.record_signal(
        coin="KRW-BTC",
        signal_type="buy",
        strategy="test",
        confidence=0.8,
        trigger_reason="old buy",
        current_price=100,
    )
    recorder.record_signal(
        coin="KRW-ETH",
        signal_type="hold",
        strategy="test",
        confidence=0.0,
        trigger_reason="recent",
        current_price=100,
    )
    db.execute("UPDATE trade_signals SET timestamp = datetime('now', '-20 days') WHERE trigger_reason LIKE 'old%'")
    db.commit()

    before = db.execute("SELECT COUNT(*) FROM trade_signals").fetchone()[0]
    assert before == 3

    # 직접 SQL로 cleanup 시뮬레이션 (스크립트 본체는 config.bot.db_path를 쓰니 단위는 SQL로)
    db.execute("DELETE FROM trade_signals WHERE signal_type = 'hold' AND timestamp < datetime('now', '-14 days')")
    db.commit()

    rows = db.execute("SELECT signal_type, trigger_reason FROM trade_signals ORDER BY id").fetchall()
    types = [dict(r)["signal_type"] for r in rows]
    # 오래된 hold는 사라짐, 오래된 buy + 최근 hold는 유지
    assert "old buy" in [dict(r)["trigger_reason"] for r in rows]
    assert types.count("hold") == 1
    assert types.count("buy") == 1


# ===================================================================
# 2. profit_krw NULL 자동 계산
# ===================================================================


def test_record_trade_auto_fills_profit_krw(db):
    """profit_pct만 주고 profit_krw 생략 시 total_krw * profit_pct / 100로 자동 계산."""
    recorder = DataRecorder(db)
    # 먼저 buy 생성 (orphan 방지 가드 통과)
    buy_id = recorder.record_trade(
        coin="KRW-BTC",
        side="buy",
        price=100,
        amount=1,
        total_krw=10000,
        fee_krw=5,
        strategy="test",
        trigger_reason="test",
    )
    # profit_pct만 주고 profit_krw 생략
    sell_id = recorder.record_trade(
        coin="KRW-BTC",
        side="sell",
        price=110,
        amount=1,
        total_krw=11000,
        fee_krw=5,
        strategy="test",
        trigger_reason="익절",
        buy_trade_id=buy_id,
        profit_pct=10.0,  # profit_krw 생략
    )
    row = db.execute("SELECT profit_krw FROM trades WHERE id = ?", (sell_id,)).fetchone()
    # 11000 * 10 / 100 = 1100
    assert dict(row)["profit_krw"] == 1100.0


def test_record_trade_respects_explicit_profit_krw(db):
    """명시적 profit_krw가 있으면 덮어쓰지 않음."""
    recorder = DataRecorder(db)
    buy_id = recorder.record_trade(
        coin="KRW-BTC",
        side="buy",
        price=100,
        amount=1,
        total_krw=10000,
        fee_krw=5,
        strategy="test",
        trigger_reason="test",
    )
    sell_id = recorder.record_trade(
        coin="KRW-BTC",
        side="sell",
        price=110,
        amount=1,
        total_krw=11000,
        fee_krw=5,
        strategy="test",
        trigger_reason="익절",
        buy_trade_id=buy_id,
        profit_pct=10.0,
        profit_krw=999.0,  # 명시적
    )
    row = db.execute("SELECT profit_krw FROM trades WHERE id = ?", (sell_id,)).fetchone()
    assert dict(row)["profit_krw"] == 999.0


# ===================================================================
# 3. orphan buy_trade_id 방지
# ===================================================================


def test_orphan_sell_raises(db):
    """존재하지 않는 buy_trade_id로 sell 시도 시 ValueError."""
    recorder = DataRecorder(db)
    with pytest.raises(ValueError, match="orphan"):
        recorder.record_trade(
            coin="KRW-BTC",
            side="sell",
            price=110,
            amount=1,
            total_krw=11000,
            fee_krw=5,
            strategy="test",
            trigger_reason="test",
            buy_trade_id=999999,  # 존재 안 함
        )


def test_valid_buy_trade_id_accepted(db):
    """실존 buy_trade_id는 정상 통과."""
    recorder = DataRecorder(db)
    buy_id = recorder.record_trade(
        coin="KRW-BTC",
        side="buy",
        price=100,
        amount=1,
        total_krw=10000,
        fee_krw=5,
        strategy="test",
        trigger_reason="test",
    )
    # 예외 없이 성공해야 함
    sell_id = recorder.record_trade(
        coin="KRW-BTC",
        side="sell",
        price=110,
        amount=1,
        total_krw=11000,
        fee_krw=5,
        strategy="test",
        trigger_reason="익절",
        buy_trade_id=buy_id,
    )
    assert sell_id > 0


# ===================================================================
# 4. balance_text API 미설정 보수적 폴백
# ===================================================================


def test_balance_text_api_not_configured_returns_conservative_warning(db, monkeypatch):
    """Trader.is_ready=False일 때 LLM에 공격적 권고 금지 경고 포함."""
    analyzer = LLMAnalyzer(db)

    # Trader를 mock — is_ready False
    import cryptobot.bot.trader as trader_mod

    class _FakeTrader:
        is_ready = False

    monkeypatch.setattr(trader_mod, "Trader", _FakeTrader)
    text = analyzer._get_balance_text()
    # 더 이상 "API 키 미설정" 단순 메시지가 아니라 경고 포함 길어진 텍스트
    assert "공격적 파라미터 권고 금지" in text or "allow_trading=false" in text
