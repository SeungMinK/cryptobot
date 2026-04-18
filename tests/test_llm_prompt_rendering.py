"""LLM 프롬프트 렌더링 — before/after 스냅샷 회귀 테스트 (#158, Closes related #153).

운영 환경에서 LLM에 실제로 들어가던 입력을 in-memory DB에 재현해,
각 섹션 렌더링이 #153 개선 후 의도대로 동작하는지 섹션별로 검증한다.

테스트는 버그 자체를 콕 찍는 방식:
- 없어야 하는 문자열이 없고 ("0건 승률0%", "+0.0%/1h", "손익비 1:1")
- 있어야 하는 신호가 있다 ("손익비 1.54", "성과(대체): ...", "동시 보유 가능: 최대 ...")

개선 전 프롬프트 reference는 tests/fixtures/llm_prompt_before.txt 참고.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cryptobot.data.database import Database
from cryptobot.llm.analyzer import LLMAnalyzer

# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _utc_iso(offset_minutes: int = 0) -> str:
    """현재 UTC ± 분 단위 offset을 'YYYY-MM-DD HH:MM:SS' 포맷으로."""
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)).strftime("%Y-%m-%d %H:%M:%S")


def _seed_market_snapshots(db: Database) -> None:
    """실제 운영 케이스를 재현한 시장 스냅샷.

    - BTC: now/prev 동일 가격 → after에는 `+0.0%/1h` 생략되어야 함 (버그 재현용)
    - ENSO: prev 없음 → `/1h` 생략
    - ARKM: now/prev 다름 → `+4.9%/1h` 실제 표기
    - BIO: now/prev 다름 → `-1.7%/1h`
    - CARV: now/prev 다름 → `-1.2%/1h`
    - STALE: prev가 윈도 밖(-200분) → `/1h` 생략되어야 함
    """
    now = _utc_iso(0)
    prev_60 = _utc_iso(-60)  # 윈도 안 (-120 ~ -30)
    stale = _utc_iso(-200)  # 윈도 밖

    rows = [
        # (coin, timestamp, price, rsi_14, market_state)
        # --- BTC: now == prev → +0.0%/1h가 떠선 안 됨
        ("KRW-BTC", prev_60, 101_877_000, 50, "bearish"),
        ("KRW-BTC", now, 101_877_000, 50, "bearish"),
        # --- ENSO: prev 아예 없음
        ("KRW-ENSO", now, 1_436, 18, "bearish"),
        # --- ARKM: prev 184 → now 193 (+4.9%)
        ("KRW-ARKM", prev_60, 184, 70, "bullish"),
        ("KRW-ARKM", now, 193, 76, "bullish"),
        # --- BIO: prev 53 → now 52 (-1.88%)
        ("KRW-BIO", prev_60, 53, 88, "bullish"),
        ("KRW-BIO", now, 52, 93, "bullish"),
        # --- CARV: prev 89 → now 88 (-1.12%)
        ("KRW-CARV", prev_60, 89, 62, "bearish"),
        ("KRW-CARV", now, 88, 58, "bearish"),
        # --- STALE: prev는 200분 전(윈도 밖) → /1h 없어야 함
        ("KRW-STALE", stale, 100, 40, "sideways"),
        ("KRW-STALE", now, 110, 45, "sideways"),
    ]
    for coin, ts, price, rsi, state in rows:
        db.execute(
            """INSERT INTO market_snapshots (timestamp, coin, price, rsi_14, market_state)
               VALUES (?, ?, ?, ?, ?)""",
            (ts, coin, price, rsi, state),
        )
    db.commit()


def _seed_backtest_results(db: Database) -> None:
    """백테스트 결과 — 0건 rows 다수 + 실제 rows 혼재."""
    # 실제 값이 있는 rows (coin, strategy, return, trades, win_rate)
    valid_rows = [
        # BTC: 실제 값 7건 — Top 5로 잘려야 함
        ("KRW-BTC", "volatility_breakout", 5.7, 10, 80.0, {"k_value": 0.7}),
        ("KRW-BTC", "ma_crossover", 4.2, 2, 100.0, {"short_period": 10, "long_period": 20}),
        ("KRW-BTC", "bb_rsi_combined", 3.4, 2, 50.0, {"bb_std": 2, "rsi_oversold": 25}),
        ("KRW-BTC", "bb_rsi_combined", 3.4, 2, 50.0, {"bb_std": 2, "rsi_oversold": 30}),
        ("KRW-BTC", "bb_rsi_combined", 3.4, 2, 50.0, {"bb_std": 2, "rsi_oversold": 35}),
        ("KRW-BTC", "ma_crossover", 1.4, 2, 100.0, {"short_period": 5, "long_period": 40}),
        ("KRW-BTC", "ma_crossover", 1.0, 1, 100.0, {"short_period": 10, "long_period": 40}),
        # SKR: 실제 값 1건만 (나머지는 0건 rows로 아래에서 추가)
        ("KRW-SKR", "bollinger_bands", 1.7, 1, 100.0, {"bb_period": 20, "bb_std": 2}),
        # 0G: 실제 값 2건
        ("KRW-0G", "volatility_breakout", 22.5, 11, 64.0, {"k_value": 0.7}),
        ("KRW-0G", "bollinger_bands", 13.1, 3, 100.0, {"bb_period": 20, "bb_std": 2}),
    ]
    # 0건 noise rows (필터에서 제외되어야 함)
    zero_rows = [
        ("KRW-BTC", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 1.5}),
        ("KRW-BTC", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 2}),
        ("KRW-BTC", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 2.5}),
        ("KRW-SKR", "bb_rsi_combined", 0.0, 0, 0.0, {"bb_std": 2}),
        ("KRW-SKR", "bollinger_bands", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 2.5}),
        ("KRW-SKR", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 1.5}),
        ("KRW-SKR", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 2}),
        ("KRW-SKR", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 2.5}),
        ("KRW-SKR", "breakout_momentum", 0.0, 0, 0.0, {"entry_period": 10, "exit_period": 10}),
        ("KRW-SKR", "breakout_momentum", 0.0, 0, 0.0, {"entry_period": 20, "exit_period": 10}),
        ("KRW-0G", "bollinger_squeeze", 0.0, 0, 0.0, {"bb_period": 20, "bb_std": 1.5}),
    ]
    run_date = "2026-04-17"
    for coin, strat, ret, trades, win_rate, params in valid_rows + zero_rows:
        db.execute(
            """INSERT INTO backtest_results
               (run_date, strategy_name, coin, period, num_trades, win_rate,
                total_return_pct, max_drawdown_pct, sharpe_ratio,
                avg_profit_pct, avg_loss_pct, best_trade_pct, worst_trade_pct, params_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_date,
                strat,
                coin,
                "2025-12-05 ~ 2026-04-05",
                trades,
                win_rate,
                ret,
                -7.0 if trades > 0 else 0.0,
                3.0 if trades > 0 else 0.0,
                2.0,
                -1.0,
                4.0,
                -2.0,
                json.dumps(params),
            ),
        )
    db.commit()


def _seed_news(db: Database) -> None:
    """뉴스 5건 (BTC 편중 + altcoin)."""
    now = _utc_iso(0)
    articles = [
        ("cointelegraph", "Ex-Treasury chief warns of US bond crash", "macro negative news body", None, "negative"),
        ("cointelegraph", "Russia-linked Grinex halts trading after hack", "hack incident", None, "negative"),
        ("coindesk", "Bitcoin bulls target $125K as peace talks trigger risk-on", "BTC analysis", "BTC", "positive"),
        ("cointelegraph", "Three things BTC must do to hold highs above $76K", "BTC analysis", "BTC", "positive"),
        ("cointelegraph", "HIVE plans $75M raise for AI infrastructure", "miner funding", "BTC", "neutral"),
    ]
    for src, title, summary, coins, sentiment in articles:
        db.execute(
            """INSERT INTO news_articles
               (source, title, summary, coins_mentioned, sentiment_keyword, published_at, collected_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (src, title, summary, coins, sentiment, now, now),
        )
    db.commit()


def _seed_trades(db: Database) -> None:
    """최근 24h 매매 8건 (승 7, 패 1) — 평균 승 2.14%, 평균 패 1.39% → 손익비 1.54."""
    # 승률 7/8 = 87.5% → 반올림 88%. 평균 승: (0.30+0.60+2.05+2.26+2.20+6.18+1.39)/7 = 14.98/7 ≈ 2.14
    rows = [
        ("KRW-SKR", 0.30, 300, "ROI 도달", 7877),
        ("KRW-BCH", 0.60, 500, "ROI 도달", 188),
        ("KRW-JST", 2.05, 1500, "ROI 도달", 47),
        ("KRW-BCH", 2.26, 1800, "ROI 도달", 6162),
        ("KRW-MOVE", 2.20, 1700, "ROI 도달", 3556),
        ("KRW-ETHFI", 6.18, 4500, "ROI 도달", 3585),
        ("KRW-CARV", 1.39, 900, "ROI 도달", 3541),
        ("KRW-TRUMP", -1.39, -900, "RSI(50) 정상 복귀", 9302),
    ]
    base = datetime.now(timezone.utc) - timedelta(hours=12)
    for i, (coin, pct, krw, reason, hold) in enumerate(rows):
        ts = (base + timedelta(minutes=i * 20)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """INSERT INTO trades
               (timestamp, coin, side, price, amount, total_krw, fee_krw, strategy,
                trigger_reason, profit_pct, profit_krw, hold_duration_minutes)
               VALUES (?, ?, 'sell', 1000, 1, 10000, 5, 'bb_rsi_combined', ?, ?, ?, ?)""",
            (ts, coin, reason, pct, krw, hold),
        )
    db.commit()


def _seed_llm_decisions(db: Database) -> None:
    """이전 분석 3건 — 모두 evaluation_period_pnl_pct=NULL (미평가 상태 재현)."""
    base = datetime.now(timezone.utc) - timedelta(hours=3)
    configs = [
        {"stop_loss_pct": -5.0, "trailing_stop_pct": -2.5, "k_value": 0.25, "max_position_per_coin_pct": 50},
        {"stop_loss_pct": -5.0, "trailing_stop_pct": -2.5, "k_value": 0.25, "max_position_per_coin_pct": 55},
        {"stop_loss_pct": -5.0, "trailing_stop_pct": -2.5, "k_value": 0.25, "max_position_per_coin_pct": 60},
    ]
    for i, cfg in enumerate(configs):
        ts = (base - timedelta(minutes=i * 10)).strftime("%Y-%m-%d %H:%M:%S")
        summary = json.dumps({"after": cfg})
        db.execute(
            """INSERT INTO llm_decisions
               (timestamp, model, output_market_state, output_aggression, output_allow_trading,
                input_news_summary)
               VALUES (?, 'claude-haiku-test', 'bearish', 0.5, 1, ?)""",
            (ts, summary),
        )
    db.commit()


def _seed_fear_greed(db: Database) -> None:
    """F&G 4건 — 21 Extreme Fear 유지."""
    now = datetime.now(timezone.utc)
    for i in range(4):
        ts = (now - timedelta(hours=i)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(
            """INSERT INTO fear_greed_index (timestamp, value, classification, collected_at)
               VALUES (?, 21, 'Extreme Fear', ?)""",
            (ts, ts),
        )
    db.commit()


def _set_bot_config(db: Database, key: str, value: str) -> None:
    """bot_config 값 설정. initialize()가 기본값을 이미 넣어뒀다고 가정하고 UPDATE."""
    db.execute("UPDATE bot_config SET value = ? WHERE key = ?", (value, key))
    db.commit()


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def populated_analyzer():
    """실제 운영 입력을 재현한 DB + LLMAnalyzer."""
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "test.db")
    db.initialize()

    _seed_market_snapshots(db)
    _seed_backtest_results(db)
    _seed_news(db)
    _seed_trades(db)
    _seed_llm_decisions(db)
    _seed_fear_greed(db)
    _set_bot_config(db, "max_position_per_coin_pct", "50")

    analyzer = LLMAnalyzer(db)
    yield analyzer, db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBacktestSection:
    """백테스트 섹션 — 0건 row 필터 + Top N per coin."""

    def test_no_zero_trade_rows(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text, _ = analyzer._get_backtest_text()

        # 개선 전: `0건 승률0%` 노이즈 다수 포함. 개선 후: 0번 등장해야 함.
        assert "0건 승률0%" not in text
        assert "+0.0%" not in text

    def test_top_n_per_coin(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text, _ = analyzer._get_backtest_text()

        # [KRW-BTC] 섹션 이후 다음 [코인] 전까지의 strategy 라인 수가 TOP_N 이하
        btc_section = _extract_coin_section(text, "KRW-BTC")
        strat_lines = [ln for ln in btc_section.splitlines() if ln.startswith("  ") and ":" in ln]
        assert len(strat_lines) <= LLMAnalyzer.TOP_N_PER_COIN

    def test_skr_mostly_zero_means_only_one_valid_row(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text, _ = analyzer._get_backtest_text()

        # SKR은 실제 값 1건 + 0건 9건 → after엔 1건만 남아야 함
        skr_section = _extract_coin_section(text, "KRW-SKR")
        strat_lines = [ln for ln in skr_section.splitlines() if ln.startswith("  ") and ":" in ln]
        assert len(strat_lines) == 1
        assert "bollinger_bands" in skr_section


class TestMarketSection:
    """시장 섹션 — prev 윈도 제한 + 동일 가격 시 /1h 생략."""

    def test_no_zero_pct_when_prices_identical(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text = analyzer._get_market_text()
        btc_line = _find_line(text, "BTC:")

        # BTC는 now==prev → 개선 전엔 +0.0%/1h 찍혔던 게 개선 후엔 사라져야 함
        assert "/1h" not in btc_line, f"BTC 라인에 잘못된 1h 표기: {btc_line!r}"

    def test_no_pct_when_prev_missing(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text = analyzer._get_market_text()
        enso_line = _find_line(text, "ENSO:")
        assert "/1h" not in enso_line

    def test_no_pct_when_prev_is_stale(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text = analyzer._get_market_text()
        stale_line = _find_line(text, "STALE:")
        # prev가 -200분 → 윈도 밖 → 매칭 안 되므로 /1h 생략
        assert "/1h" not in stale_line

    def test_actual_pct_change_shown_when_prices_differ(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text = analyzer._get_market_text()

        arkm_line = _find_line(text, "ARKM:")
        bio_line = _find_line(text, "BIO:")
        carv_line = _find_line(text, "CARV:")

        # ARKM 184→193 = +4.89% ≈ +4.9%
        assert re.search(r"\(\+4\.\d%/1h\)", arkm_line), arkm_line
        # BIO 53→52 = -1.88% ≈ -1.9%
        assert re.search(r"\(-1\.\d%/1h\)", bio_line), bio_line
        # CARV 89→88 = -1.12% ≈ -1.1%
        assert re.search(r"\(-1\.\d%/1h\)", carv_line), carv_line


class TestPerformanceSection:
    """성과 섹션 — 손익비 계산·표기."""

    def test_reward_risk_ratio_decimal_format(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text = analyzer._get_performance_text()

        # 개선 전: `손익비 1:1` 식 반올림 버그
        assert "손익비 1:1" not in text
        assert "손익비 1:" not in text  # 어떤 1:X 포맷도 없어야

        # 개선 후: `손익비 X.XX` (소수점 2자리). 평균 승 2.14 / 평균 패 1.39 ≈ 1.54
        match = re.search(r"손익비 (\d+\.\d{2})", text)
        assert match is not None, text
        assert abs(float(match.group(1)) - 1.54) < 0.05, match.group(1)

    def test_target_reward_risk_goal_shown(self, populated_analyzer):
        analyzer, _ = populated_analyzer
        text = analyzer._get_performance_text()
        assert "목표 ≥ 1.5" in text


class TestPreviousFeedbackSection:
    """이전 분석 피드백 — 매매 없을 때도 대체 평가 기록."""

    def test_proxy_metric_when_no_trades(self, populated_analyzer):
        analyzer, db = populated_analyzer
        # 이전 llm_decision 이후 매매 0건 조건 만들기: 기존 trades의 timestamp를
        # llm_decision 시점보다 더 과거로 밀어서 "직전 이후 매매 0건" 상태 유도
        db.execute("UPDATE trades SET timestamp = datetime('now', '-48 hours')")
        db.commit()

        text = analyzer._get_previous_feedback()

        # 개선 전: 3회 연속 '성과: 미평가'
        # 개선 후: '성과(대체): 매매 0건, BTC ...'
        assert "성과(대체):" in text
        assert "매매 0건" in text


class TestBalanceSection:
    """잔고 섹션 — 동시 보유 가능 종목 수 힌트."""

    def test_slot_hint_line_present(self, populated_analyzer):
        analyzer, _ = populated_analyzer

        # Trader는 외부 API 의존이라 mock 처리
        fake_trader = MagicMock()
        fake_trader.is_ready = True
        fake_trader.get_balance_krw.return_value = 99_442

        with patch("cryptobot.bot.trader.Trader", return_value=fake_trader):
            text = analyzer._get_balance_text()

        assert "동시 보유 가능: 최대" in text
        assert "max_position_per_coin_pct=50%" in text


class TestAnalysisPromptTextRules:
    """프롬프트 규칙 블록 — should_alert_stop 기준, 손익비 목표 표기."""

    def test_should_alert_stop_criteria_block_present(self):
        # #183: 규칙 블록은 SYSTEM_PROMPT로 이동 (Prompt Caching).
        # SYSTEM + ANALYSIS 합쳐서 검증.
        from cryptobot.llm.analyzer import ANALYSIS_PROMPT, SYSTEM_PROMPT

        ANALYSIS_PROMPT = SYSTEM_PROMPT + "\n" + ANALYSIS_PROMPT  # noqa: F811 — 로컬 변수로 오버라이드

        # 개선 전: "시장이 극도로 위험하면 should_alert_stop = true" 한 줄
        # 개선 후: 4개 구체 기준을 나열
        assert "should_alert_stop = true 조건" in ANALYSIS_PROMPT
        assert "공포/탐욕 지수 10 이하" in ANALYSIS_PROMPT
        assert "보유 포지션 평균 미실현 -10% 이상" in ANALYSIS_PROMPT
        assert "거시 충격 뉴스" in ANALYSIS_PROMPT

    def test_fear_greed_neutralized(self):
        # #183: 규칙 블록은 SYSTEM_PROMPT로 이동 (Prompt Caching).
        # SYSTEM + ANALYSIS 합쳐서 검증.
        from cryptobot.llm.analyzer import ANALYSIS_PROMPT, SYSTEM_PROMPT

        ANALYSIS_PROMPT = SYSTEM_PROMPT + "\n" + ANALYSIS_PROMPT  # noqa: F811 — 로컬 변수로 오버라이드

        # 개선 전: "역사적 매수 적기 (7년 백테스트 1,145% 수익)"
        # 개선 후: "단기 추가 하락 위험도 공존"
        assert "단기 추가 하락 위험도 공존" in ANALYSIS_PROMPT
        assert "1,145%" not in ANALYSIS_PROMPT

    def test_reward_risk_goal_1p5(self):
        # #183: 규칙 블록은 SYSTEM_PROMPT로 이동 (Prompt Caching).
        # SYSTEM + ANALYSIS 합쳐서 검증.
        from cryptobot.llm.analyzer import ANALYSIS_PROMPT, SYSTEM_PROMPT

        ANALYSIS_PROMPT = SYSTEM_PROMPT + "\n" + ANALYSIS_PROMPT  # noqa: F811 — 로컬 변수로 오버라이드

        # 개선 후: "1.5 이상을 목표"로 표기 일관화
        assert "1.5 이상" in ANALYSIS_PROMPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_line(text: str, prefix: str) -> str:
    """시장 섹션에서 `{코인}:` 라인 찾기. 없으면 빈 문자열."""
    for line in text.splitlines():
        if line.startswith(prefix):
            return line
    return ""


def _extract_coin_section(text: str, coin: str) -> str:
    """백테스트 텍스트에서 `[{coin}]` ~ 다음 `[` 전까지 잘라내기."""
    lines = text.splitlines()
    out: list[str] = []
    in_section = False
    for ln in lines:
        if ln.startswith(f"[{coin}]"):
            in_section = True
            out.append(ln)
            continue
        if in_section:
            if ln.startswith("[") or ln.startswith("### "):
                break
            out.append(ln)
    return "\n".join(out)
