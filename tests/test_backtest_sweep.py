"""백테스트 파라미터 스윕 + LLM 프롬프트 개선 테스트."""

import json
import sqlite3

from cryptobot.backtest.reporter import SWEEP_CONFIGS, BacktestReporter
from cryptobot.llm.analyzer import LLMAnalyzer


class TestGenerateSweepCombos:
    """_generate_sweep_combos 조합 생성 테스트."""

    def test_single_param_three_values(self):
        """단일 파라미터 3값 → 3개 조합."""
        base = {"a": 1, "b": 2}
        sweep = {"k_value": [0.3, 0.5, 0.7]}
        combos = BacktestReporter._generate_sweep_combos(base, sweep)
        assert len(combos) == 3
        assert combos[0] == {"a": 1, "b": 2, "k_value": 0.3}
        assert combos[1] == {"a": 1, "b": 2, "k_value": 0.5}
        assert combos[2] == {"a": 1, "b": 2, "k_value": 0.7}

    def test_two_params_product(self):
        """2개 파라미터 (3 × 2) → 6개 조합."""
        base = {"x": 10}
        sweep = {"rsi_oversold": [25, 30, 35], "bb_std": [1.5, 2.0]}
        combos = BacktestReporter._generate_sweep_combos(base, sweep)
        assert len(combos) == 6
        # 모든 조합이 base 값 유지
        for c in combos:
            assert c["x"] == 10
        # 모든 bb_rsi_combined 조합 확인
        rsi_values = {c["rsi_oversold"] for c in combos}
        bb_values = {c["bb_std"] for c in combos}
        assert rsi_values == {25, 30, 35}
        assert bb_values == {1.5, 2.0}

    def test_override_base_param(self):
        """스윕 값이 기본 파라미터를 덮어쓰는지 확인."""
        base = {"k_value": 0.5, "other": 99}
        sweep = {"k_value": [0.3, 0.7]}
        combos = BacktestReporter._generate_sweep_combos(base, sweep)
        assert len(combos) == 2
        assert combos[0]["k_value"] == 0.3
        assert combos[1]["k_value"] == 0.7
        assert all(c["other"] == 99 for c in combos)

    def test_empty_sweep(self):
        """빈 스윕 → itertools.product가 1개 빈 튜플 반환."""
        base = {"a": 1}
        combos = BacktestReporter._generate_sweep_combos(base, {})
        assert len(combos) == 1
        assert combos[0] == {"a": 1}


class TestSweepConfigsCoverage:
    """SWEEP_CONFIGS가 모든 전략을 커버하는지 확인."""

    def test_all_strategies_have_sweep(self):
        """STRATEGY_CLASSES의 모든 전략이 SWEEP_CONFIGS에 있는지 확인."""
        from cryptobot.bot.strategy_selector import STRATEGY_CLASSES

        for name in STRATEGY_CLASSES:
            assert name in SWEEP_CONFIGS, f"전략 '{name}'이 SWEEP_CONFIGS에 없음"

    def test_sweep_values_are_lists(self):
        """스윕 값이 모두 리스트인지 확인."""
        for strategy, params in SWEEP_CONFIGS.items():
            for key, values in params.items():
                assert isinstance(values, list), f"{strategy}.{key}가 리스트가 아님"
                assert len(values) >= 2, f"{strategy}.{key}에 값이 2개 미만"


class TestFormatKeyParams:
    """_format_key_params 파라미터 표시 테스트."""

    def test_volatility_breakout(self):
        """변동성 돌파 전략 파라미터 표시."""
        result = BacktestReporter._format_key_params({"k_value": 0.7}, "volatility_breakout")
        assert result == "(k=0.7)"

    def test_bb_rsi_combined(self):
        """BB RSI 복합 전략 파라미터 표시."""
        result = BacktestReporter._format_key_params({"rsi_oversold": 35, "bb_std": 1.5}, "bb_rsi_combined")
        assert "rsi_os=35" in result
        assert "bb=1.5" in result

    def test_no_sweep_config(self):
        """스윕 설정 없는 전략 → 빈 문자열."""
        result = BacktestReporter._format_key_params({"k_value": 0.5}, "unknown_strategy")
        assert result == ""

    def test_integer_display(self):
        """정수값은 정수로 표시."""
        result = BacktestReporter._format_key_params({"grid_count": 10.0}, "grid_trading")
        assert "grid=10" in result
        assert "10.0" not in result


def _create_test_db() -> sqlite3.Connection:
    """테스트용 인메모리 DB 생성."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""
        CREATE TABLE backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT,
            strategy_name TEXT,
            coin TEXT,
            period TEXT,
            num_trades INTEGER,
            win_rate REAL,
            total_return_pct REAL,
            max_drawdown_pct REAL,
            sharpe_ratio REAL,
            avg_profit_pct REAL,
            avg_loss_pct REAL,
            best_trade_pct REAL,
            worst_trade_pct REAL,
            params_json TEXT
        )
    """)
    return db


def _insert_backtest_row(
    db: sqlite3.Connection,
    run_date: str,
    strategy: str,
    coin: str,
    total_return_pct: float,
    params: dict | None = None,
) -> None:
    """백테스트 결과 1건 삽입."""
    db.execute(
        """INSERT INTO backtest_results
           (run_date, strategy_name, coin, period, num_trades, win_rate,
            total_return_pct, max_drawdown_pct, sharpe_ratio,
            avg_profit_pct, avg_loss_pct, best_trade_pct, worst_trade_pct, params_json)
           VALUES (?, ?, ?, '2026-03-01 ~ 2026-04-13', 5, 60.0,
                   ?, -3.0, 1.5, 2.0, -1.0, 4.0, -2.0, ?)""",
        (run_date, strategy, coin, total_return_pct, json.dumps(params or {})),
    )


class TestBacktestTextWithParams:
    """_get_backtest_text 파라미터 표시 테스트."""

    def test_params_in_text(self):
        """파라미터가 프롬프트 텍스트에 포함되는지 확인."""
        db = _create_test_db()
        _insert_backtest_row(db, "2026-04-13", "volatility_breakout", "KRW-BTC", 2.3, {"k_value": 0.7})
        db.commit()

        analyzer = LLMAnalyzer.__new__(LLMAnalyzer)
        analyzer._db = db

        text, run_date = analyzer._get_backtest_text()
        assert "k=0.7" in text
        assert "volatility_breakout" in text
        assert "+2.3%" in text
        assert run_date == "2026-04-13"

    def test_common_params_excluded(self):
        """공통 파라미터(stop_loss_pct 등)는 표시되지 않는지 확인."""
        db = _create_test_db()
        params = {"k_value": 0.5, "stop_loss_pct": -5.0, "trailing_stop_pct": -3.0}
        _insert_backtest_row(db, "2026-04-13", "volatility_breakout", "KRW-BTC", 1.0, params)
        db.commit()

        text = LLMAnalyzer._format_backtest_params(json.dumps(params), "volatility_breakout")
        assert "k=0.5" in text
        assert "stop_loss" not in text
        assert "trailing" not in text


class TestBacktestTextTopNLimit:
    """코인당 Top N 제한 테스트."""

    def test_top_n_limit(self):
        """코인당 TOP_N_PER_COIN개만 표시되는지 확인."""
        db = _create_test_db()
        # 15개 결과 삽입 (Top N만 표시되어야 함)
        for i in range(15):
            _insert_backtest_row(
                db,
                "2026-04-13",
                f"strategy_{i}",
                "KRW-BTC",
                10.0 - i,
                {"param": i},
            )
        db.commit()

        analyzer = LLMAnalyzer.__new__(LLMAnalyzer)
        analyzer._db = db

        text, _ = analyzer._get_backtest_text()
        top_n = LLMAnalyzer.TOP_N_PER_COIN
        # strategy_0 ~ strategy_(N-1) (Top N) 있어야 함
        for i in range(top_n):
            assert f"strategy_{i}" in text
        # strategy_N ~ strategy_14 (나머지) 없어야 함
        for i in range(top_n, 15):
            assert f"strategy_{i}" not in text


class TestBacktestTextTwoRuns:
    """2회분 결과 포함 테스트."""

    def test_two_run_dates(self):
        """최근 2회 실행일의 결과가 모두 포함되는지 확인."""
        db = _create_test_db()
        _insert_backtest_row(db, "2026-04-13", "volatility_breakout", "KRW-BTC", 2.3, {"k_value": 0.7})
        _insert_backtest_row(db, "2026-04-06", "volatility_breakout", "KRW-BTC", 1.1, {"k_value": 0.5})
        db.commit()

        analyzer = LLMAnalyzer.__new__(LLMAnalyzer)
        analyzer._db = db

        text, run_date = analyzer._get_backtest_text()
        assert "최근 실행: 2026-04-13" in text
        assert "이전 실행: 2026-04-06" in text
        assert run_date == "2026-04-13"

    def test_single_run_date(self):
        """1회분만 있으면 '이전 실행' 없이 표시."""
        db = _create_test_db()
        _insert_backtest_row(db, "2026-04-13", "macd", "KRW-ETH", 3.5, {"fast": 12, "slow": 26})
        db.commit()

        analyzer = LLMAnalyzer.__new__(LLMAnalyzer)
        analyzer._db = db

        text, _ = analyzer._get_backtest_text()
        assert "최근 실행: 2026-04-13" in text
        assert "이전 실행" not in text

    def test_three_dates_only_latest_two(self):
        """3회분 있어도 최근 2회만 표시."""
        db = _create_test_db()
        _insert_backtest_row(db, "2026-04-13", "macd", "KRW-BTC", 3.0)
        _insert_backtest_row(db, "2026-04-06", "macd", "KRW-BTC", 2.0)
        _insert_backtest_row(db, "2026-03-30", "macd", "KRW-BTC", 1.0)
        db.commit()

        analyzer = LLMAnalyzer.__new__(LLMAnalyzer)
        analyzer._db = db

        text, _ = analyzer._get_backtest_text()
        assert "2026-04-13" in text
        assert "2026-04-06" in text
        assert "2026-03-30" not in text
