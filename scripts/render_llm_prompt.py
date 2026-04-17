#!/usr/bin/env python3
"""LLM 프롬프트 렌더링 도구 — 실제 DB에서 프롬프트가 어떻게 나오는지 확인.

Claude API를 **실제로 호출하지 않고**, `LLMAnalyzer`가 조립하는 프롬프트
문자열만 stdout으로 출력한다. 프롬프트 개선안을 돌려보거나, 운영 DB를
대상으로 현재 코드의 출력을 확인할 때 유용.

사용:
    # 기본 운영 DB
    python scripts/render_llm_prompt.py

    # 지정 DB
    python scripts/render_llm_prompt.py --db /path/to/cryptobot.db

    # 특정 섹션만 출력
    python scripts/render_llm_prompt.py --section market
    python scripts/render_llm_prompt.py --section backtest

섹션 이름은 LLMAnalyzer가 format에 넘기는 템플릿 변수와 동일:
    news, fear_greed, market, balance, performance, previous_feedback,
    current_strategy_params, active_strategy, strategies, param_stats,
    backtest, full (전체 조립 결과)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cryptobot.data.database import Database  # noqa: E402
from cryptobot.llm.analyzer import ANALYSIS_PROMPT, LLMAnalyzer  # noqa: E402

DEFAULT_DB_PATH = str(PROJECT_ROOT / "data" / "cryptobot.db")


# 섹션 이름 → LLMAnalyzer 메서드 매핑.
# `_get_backtest_text`처럼 튜플 반환인 경우 첫 번째 요소 사용.
SECTION_METHODS = {
    "news": ("_get_news_text", False),
    "fear_greed": ("_get_fear_greed_text", False),
    "market": ("_get_market_text", False),
    "balance": ("_get_balance_text", False),
    "performance": ("_get_performance_text", False),
    "previous_feedback": ("_get_previous_feedback", False),
    "current_strategy_params": ("_get_current_strategy_params", False),
    "active_strategy": ("_get_active_strategy_text", False),
    "strategies": ("_get_strategies_text", False),
    "param_stats": ("_get_param_stats_text", False),
    "backtest": ("_get_backtest_text", True),  # (text, run_date) 튜플
}


def render_section(analyzer: LLMAnalyzer, name: str) -> str:
    """지정 섹션 렌더링."""
    if name == "full":
        return _render_full(analyzer)

    if name not in SECTION_METHODS:
        raise SystemExit(f"알 수 없는 섹션: {name!r}. 가능: {list(SECTION_METHODS) + ['full']}")

    method_name, is_tuple = SECTION_METHODS[name]
    result = getattr(analyzer, method_name)()
    return result[0] if is_tuple else result


def _render_full(analyzer: LLMAnalyzer) -> str:
    """전체 프롬프트 조립. `analyze()`가 실제 호출 시 만드는 문자열과 동일."""
    backtest_text, _ = analyzer._get_backtest_text()
    return ANALYSIS_PROMPT.format(
        news_text=analyzer._get_news_text(),
        fear_greed_text=analyzer._get_fear_greed_text(),
        market_text=analyzer._get_market_text(),
        balance_text=analyzer._get_balance_text(),
        performance_text=analyzer._get_performance_text(),
        previous_feedback=analyzer._get_previous_feedback(),
        current_strategy_params=analyzer._get_current_strategy_params(),
        active_strategy_text=analyzer._get_active_strategy_text(),
        strategies_text=analyzer._get_strategies_text(),
        param_stats_text=analyzer._get_param_stats_text(),
        backtest_text=backtest_text,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help=f"DB 경로 (기본: {DEFAULT_DB_PATH})")
    parser.add_argument(
        "--section",
        default="full",
        help="출력할 섹션 (기본: full). 가능: "
        + ", ".join(sorted(list(SECTION_METHODS) + ["full"])),
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"DB 파일 없음: {db_path}", file=sys.stderr)
        return 1

    db = Database(db_path)
    db.initialize()
    analyzer = LLMAnalyzer(db)

    output = render_section(analyzer, args.section)
    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
