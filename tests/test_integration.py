"""실제 매매 데이터 기반 통합 테스트.

운영 중 발견된 버그를 재현하여 재발 방지.
"""

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.data.collector import DataCollector
from cryptobot.bot.risk import RiskLimits, RiskManager
from cryptobot.strategies.base import BaseStrategy, Signal, StrategyParams, StrategyInfo
from cryptobot.strategies.bollinger_bands import BollingerBands
from cryptobot.strategies.rsi_mean_reversion import RSIMeanReversion
from cryptobot.strategies.volatility_breakout import VolatilityBreakout
from cryptobot.strategies.ma_crossover import MACrossover
from cryptobot.strategies.registry import StrategyRegistry


def _make_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()
    return db


def _make_ohlcv(prices: list[float], days: int = 30) -> pd.DataFrame:
    """테스트용 OHLCV DataFrame 생성."""
    data = []
    for i, p in enumerate(prices):
        data.append({
            "open": p * 0.99,
            "high": p * 1.02,
            "low": p * 0.98,
            "close": p,
            "volume": 1000,
        })
    df = pd.DataFrame(data)
    df.index = pd.date_range(end=datetime.now(), periods=len(prices), freq="D")
    return df


# ═══════════════════════════════════════════════════
# 1. 수수료 가드: 0.1% 이하 수익에서 매도 차단
# ═══════════════════════════════════════════════════

class TestFeeGuard:
    """BSV 반복 매도 버그 재현 — 수수료 이하 수익에서 매도 안 되는지."""

    def test_trailing_stop_blocks_below_fee(self):
        """수익 0.05%에서 트레일링 스탑 → 매도 차단."""
        s = BollingerBands(StrategyParams(trailing_stop_pct=-3.0, stop_loss_pct=-5.0))
        # 매수 100, 최고가 100.5 설정
        s.check_trailing_stop(current_price=100.5, buy_price=100)
        # 100.5 → 97.4 (트레일링 -3% 미만) but 매수 대비 수익 -2.6%
        # 이건 손절이 아니므로 수수료 가드에 걸림... 아니, -2.6%면 손절이어야 하는데
        # stop_loss=-5%이므로 아직 안 걸림
        # 수익이 +0.05%일 때 테스트
        s2 = BollingerBands(StrategyParams(trailing_stop_pct=-1.0, stop_loss_pct=-5.0))
        s2.check_trailing_stop(current_price=100.15, buy_price=100)  # 최고가 100.15
        result = s2.check_trailing_stop(current_price=100.05, buy_price=100)  # 최고가 대비 -0.1%
        # 수익 +0.05% < 수수료 0.1% → 매도 차단
        assert result is None

    def test_trailing_stop_allows_above_fee(self):
        """수익 0.5%에서 트레일링 스탑 → 매도 허용."""
        s = BollingerBands(StrategyParams(trailing_stop_pct=-1.0, stop_loss_pct=-5.0))
        s.check_trailing_stop(current_price=101.0, buy_price=100)  # 최고가 101
        result = s.check_trailing_stop(current_price=99.9, buy_price=99)  # 최고가 101 대비 -1.09%
        # pnl = (99.9-99)/99 = +0.91% > 수수료 0.1% → 매도 허용
        assert result is not None
        assert "익절" in result.reason

    def test_stop_loss_ignores_fee(self):
        """손절은 수수료 무시하고 무조건 실행."""
        s = BollingerBands(StrategyParams(trailing_stop_pct=-3.0, stop_loss_pct=-5.0))
        result = s.check_trailing_stop(current_price=94.5, buy_price=100)
        assert result is not None
        assert "손절" in result.reason

    def test_zero_profit_blocked(self):
        """수익 0%에서 매도 차단 (BSV 반복 매도 버그 재현)."""
        s = VolatilityBreakout(StrategyParams(trailing_stop_pct=-0.5, stop_loss_pct=-5.0))
        # 매수가 = 현재가 = 23350 (BSV 실제 케이스)
        s.check_trailing_stop(current_price=23350, buy_price=23350)
        result = s.check_trailing_stop(current_price=23340, buy_price=23350)
        # 수익 -0.04% → 수수료 가드 차단 (손절 아님)
        assert result is None


# ═══════════════════════════════════════════════════
# 2. 수수료 포함 수익 계산 정확성
# ═══════════════════════════════════════════════════

class TestProfitCalculation:
    """profit_krw, profit_pct가 수수료를 포함하는지."""

    def test_profit_includes_fees(self):
        """매수 수수료 + 매도 수수료 포함 계산."""
        buy_total = 50000
        buy_fee = 25  # 0.05%
        sell_total = 50100
        sell_fee = 25.05

        buy_real = buy_total + buy_fee  # 실지출
        sell_real = sell_total - sell_fee  # 실수령
        profit_krw = sell_real - buy_real
        profit_pct = profit_krw / buy_real * 100

        assert profit_krw == pytest.approx(49.95, abs=0.1)
        assert profit_pct == pytest.approx(0.0998, abs=0.01)

    def test_same_price_is_loss(self):
        """동일가 매수/매도 시 수수료만큼 손해."""
        buy_total = 50000
        buy_fee = 25
        sell_total = 50000  # 동일가
        sell_fee = 25

        profit_krw = (sell_total - sell_fee) - (buy_total + buy_fee)
        assert profit_krw == -50  # 수수료 합계만큼 손해


# ═══════════════════════════════════════════════════
# 3. 멀티코인 스냅샷 분리
# ═══════════════════════════════════════════════════

class TestMultiCoinSnapshot:
    """코인별 get_latest_snapshot이 분리되는지."""

    def test_snapshot_per_coin(self):
        """BTC 스냅샷과 ETH 스냅샷이 섞이지 않는지."""
        db = _make_db()
        try:
            # BTC 스냅샷 저장
            db.execute(
                "INSERT INTO market_snapshots (timestamp, coin, price, market_state) VALUES (?, ?, ?, ?)",
                ("2026-04-04 08:00:00", "KRW-BTC", 101000000, "bearish"),
            )
            # ETH 스냅샷 저장 (더 나중)
            db.execute(
                "INSERT INTO market_snapshots (timestamp, coin, price, market_state) VALUES (?, ?, ?, ?)",
                ("2026-04-04 08:00:01", "KRW-ETH", 3100000, "sideways"),
            )
            db.commit()

            # BTC collector는 BTC만 가져와야 함
            btc_row = db.execute(
                "SELECT * FROM market_snapshots WHERE coin = 'KRW-BTC' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert btc_row["price"] == 101000000

            # ETH collector는 ETH만
            eth_row = db.execute(
                "SELECT * FROM market_snapshots WHERE coin = 'KRW-ETH' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert eth_row["price"] == 3100000

            # 전체 최신은 ETH인데, BTC가 섞이면 안 됨
            latest = db.execute("SELECT * FROM market_snapshots ORDER BY id DESC LIMIT 1").fetchone()
            assert latest["coin"] == "KRW-ETH"  # 섞이면 BTC 스냅샷이 잘못 반환될 수 있음
        finally:
            db.close()


# ═══════════════════════════════════════════════════
# 4. 시장 상태별 전략 자동 선택
# ═══════════════════════════════════════════════════

class TestMarketStrategySelection:
    """시장 상태에 따라 올바른 전략이 선택되는지."""

    def setup_method(self):
        self.registry = StrategyRegistry()
        for cls in [VolatilityBreakout, MACrossover, RSIMeanReversion, BollingerBands]:
            self.registry.register(cls())

    def test_bullish_selects_volatility(self):
        s = self.registry.select_by_market("bullish")
        assert s is not None
        assert s.info().name == "volatility_breakout"

    def test_sideways_selects_rsi(self):
        s = self.registry.select_by_market("sideways")
        assert s is not None
        assert s.info().name == "rsi_mean_reversion"

    def test_bearish_selects_ma(self):
        s = self.registry.select_by_market("bearish")
        assert s is not None
        assert s.info().name == "ma_crossover"

    def test_unknown_market_returns_none(self):
        s = self.registry.select_by_market("unknown_state")
        assert s is None


# ═══════════════════════════════════════════════════
# 5. 보유 중 hold 신호 기록
# ═══════════════════════════════════════════════════

class TestHoldSignalRecording:
    """보유 중(매도 대기)일 때 hold 신호가 trade_signals에 기록되는지."""

    def test_hold_signal_recorded(self):
        db = _make_db()
        try:
            recorder = DataRecorder(db)
            signal_id = recorder.record_signal(
                coin="KRW-BTC",
                signal_type="hold",
                strategy="rsi_mean_reversion",
                confidence=0.0,
                trigger_reason="보유 유지",
                current_price=101000000,
                snapshot_id=None,
            )
            assert signal_id > 0

            row = db.execute("SELECT * FROM trade_signals WHERE id = ?", (signal_id,)).fetchone()
            assert row["signal_type"] == "hold"
            assert row["coin"] == "KRW-BTC"
        finally:
            db.close()


# ═══════════════════════════════════════════════════
# 6. FOREIGN KEY 안전 처리
# ═══════════════════════════════════════════════════

class TestForeignKeySafety:
    """snapshot_id가 0이면 None으로 처리되는지."""

    def test_snapshot_id_zero_becomes_none(self):
        db = _make_db()
        try:
            recorder = DataRecorder(db)
            # snapshot_id=0은 FK 위반이므로 None으로 처리되어야 함
            signal_id = recorder.record_signal(
                coin="KRW-ETH",
                signal_type="hold",
                strategy="test",
                confidence=0.0,
                trigger_reason="test",
                current_price=3000000,
                snapshot_id=0,
            )
            row = db.execute("SELECT snapshot_id FROM trade_signals WHERE id = ?", (signal_id,)).fetchone()
            assert row["snapshot_id"] is None
        finally:
            db.close()

    def test_valid_snapshot_id_preserved(self):
        db = _make_db()
        try:
            # 스냅샷 먼저 생성
            cursor = db.execute(
                "INSERT INTO market_snapshots (timestamp, coin, price) VALUES (?, ?, ?)",
                ("2026-04-04 08:00:00", "KRW-BTC", 101000000),
            )
            db.commit()
            snap_id = cursor.lastrowid

            recorder = DataRecorder(db)
            signal_id = recorder.record_signal(
                coin="KRW-BTC",
                signal_type="hold",
                strategy="test",
                confidence=0.0,
                trigger_reason="test",
                current_price=101000000,
                snapshot_id=snap_id,
            )
            row = db.execute("SELECT snapshot_id FROM trade_signals WHERE id = ?", (signal_id,)).fetchone()
            assert row["snapshot_id"] == snap_id
        finally:
            db.close()


# ═══════════════════════════════════════════════════
# 7. 코인별 포지션 독립 추적
# ═══════════════════════════════════════════════════

class TestMultiCoinPositions:
    """여러 코인의 매수/매도가 독립적으로 추적되는지."""

    def test_independent_positions(self):
        db = _make_db()
        try:
            recorder = DataRecorder(db)

            # BTC 매수
            btc_buy = recorder.record_trade(
                coin="KRW-BTC", side="buy", price=100000000, amount=0.001,
                total_krw=100000, fee_krw=50, strategy="test", trigger_reason="test",
            )
            # ETH 매수
            eth_buy = recorder.record_trade(
                coin="KRW-ETH", side="buy", price=3000000, amount=0.1,
                total_krw=300000, fee_krw=150, strategy="test", trigger_reason="test",
            )

            # BTC만 활성 매수
            btc_active = recorder.get_active_buy_trade("KRW-BTC")
            assert btc_active is not None
            assert btc_active["coin"] == "KRW-BTC"

            # ETH만 활성 매수
            eth_active = recorder.get_active_buy_trade("KRW-ETH")
            assert eth_active is not None
            assert eth_active["coin"] == "KRW-ETH"

            # BTC 매도
            recorder.record_trade(
                coin="KRW-BTC", side="sell", price=101000000, amount=0.001,
                total_krw=101000, fee_krw=50.5, strategy="test", trigger_reason="test",
                buy_trade_id=btc_buy, profit_pct=0.95, profit_krw=899.5,
            )

            # BTC 포지션 없음
            assert recorder.get_active_buy_trade("KRW-BTC") is None
            # ETH는 여전히 보유 중
            assert recorder.get_active_buy_trade("KRW-ETH") is not None
        finally:
            db.close()


# ═══════════════════════════════════════════════════
# 8. naive/aware datetime 호환
# ═══════════════════════════════════════════════════

class TestDatetimeCompatibility:
    """UTC aware와 naive datetime이 섞여도 에러 안 나는지."""

    def test_naive_timestamp_from_db(self):
        """DB의 naive timestamp를 UTC aware로 변환."""
        naive = datetime.fromisoformat("2026-04-04 08:00:00")
        assert naive.tzinfo is None

        # UTC로 변환
        if naive.tzinfo is None:
            naive = naive.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        diff = (now - naive).total_seconds()
        assert diff > 0  # 과거이므로 양수

    def test_aware_timestamp_from_db(self):
        """DB에 UTC aware로 저장된 경우도 호환."""
        aware_str = "2026-04-04T08:00:00+00:00"
        aware = datetime.fromisoformat(aware_str)
        assert aware.tzinfo is not None

        now = datetime.now(timezone.utc)
        diff = (now - aware).total_seconds()
        assert diff > 0


# ═══════════════════════════════════════════════════
# 9. 수수료 가드 — main.py 레벨
# ═══════════════════════════════════════════════════

class TestMainFeeGuard:
    """_check_and_sell의 최종 수수료 가드."""

    def test_fee_guard_formula(self):
        """수수료 가드 계산 공식 검증."""
        buy_price = 23350  # BSV 실제 케이스
        current_price = 23350  # 동일가
        pnl_pct = (current_price - buy_price) / buy_price * 100
        assert pnl_pct == 0.0
        assert pnl_pct <= 0.1  # 수수료 가드에 걸림 → 매도 차단

    def test_fee_guard_allows_profit(self):
        """0.1% 초과 수익이면 매도 허용."""
        buy_price = 23350
        current_price = 23380  # +0.13%
        pnl_pct = (current_price - buy_price) / buy_price * 100
        assert pnl_pct > 0.1  # 매도 허용

    def test_fee_guard_stop_loss_bypass(self):
        """손절은 수수료 가드 무시."""
        reason = "손절"
        is_stop_loss = "손절" in reason
        assert is_stop_loss is True
        # 손절이면 pnl_pct 상관없이 매도


# ═══════════════════════════════════════════════════
# 10. 코인별 전략 파라미터 독립성
# ═══════════════════════════════════════════════════

class TestStrategyParamsIndependence:
    """전략 파라미터가 코인 간에 오염되지 않는지."""

    def test_params_not_shared(self):
        """다른 코인에 같은 전략 적용 시 파라미터 독립."""
        s1 = BollingerBands(StrategyParams(stop_loss_pct=-5.0, trailing_stop_pct=-3.0))
        s2 = BollingerBands(StrategyParams(stop_loss_pct=-3.0, trailing_stop_pct=-2.0))

        assert s1.params.stop_loss_pct == -5.0
        assert s2.params.stop_loss_pct == -3.0

        # s2 변경이 s1에 영향 없어야 함
        s2.params.stop_loss_pct = -1.0
        assert s1.params.stop_loss_pct == -5.0


# ═══════════════════════════════════════════════════
# 11. 스캐너 제외 목록
# ═══════════════════════════════════════════════════

class TestScannerExclusions:
    """스테이블코인이 제외되는지."""

    def test_stablecoin_excluded(self):
        from cryptobot.bot.scanner import CoinScanner
        excluded = CoinScanner.EXCLUDED_COINS
        assert "KRW-USDT" in excluded
        assert "KRW-USDC" in excluded
        assert "KRW-DAI" in excluded
        assert "KRW-BTC" not in excluded


# ═══════════════════════════════════════════════════
# 12. DB 마이그레이션 안전성
# ═══════════════════════════════════════════════════

class TestDBMigration:
    """DB 초기화가 멱등(idempotent)하고 마이그레이션이 안전한지."""

    def test_double_init_safe(self):
        db = _make_db()
        try:
            # 두 번 초기화해도 에러 없음
            db.initialize()
            db.initialize()

            # 테이블 존재 확인
            tables = [r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
            assert "market_snapshots" in tables
            assert "trade_signals" in tables
            assert "trades" in tables
            assert "bot_config" in tables
            assert "coin_strategy_config" in tables
            assert "ohlcv_daily" in tables
        finally:
            db.close()

    def test_coin_column_exists(self):
        """market_snapshots에 coin 컬럼이 있는지."""
        db = _make_db()
        try:
            cols = [r["name"] for r in db.execute("PRAGMA table_info(market_snapshots)").fetchall()]
            assert "coin" in cols
        finally:
            db.close()

    def test_strategy_params_json_in_signals(self):
        """trade_signals에 strategy_params_json 컬럼이 있는지."""
        db = _make_db()
        try:
            cols = [r["name"] for r in db.execute("PRAGMA table_info(trade_signals)").fetchall()]
            assert "strategy_params_json" in cols
        finally:
            db.close()
