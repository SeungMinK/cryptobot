#!/usr/bin/env python3
"""백테스트 CLI 러너.

단일 실행:
    python scripts/run_backtest.py --strategy volatility_breakout --coin KRW-BTC

파라미터 스윕:
    python scripts/run_backtest.py --strategy rsi_mean_reversion --coin KRW-BTC \\
        --sweep "stop_loss_pct=-3,-5,-7 trailing_stop_pct=-2,-3,-5"
"""

import argparse
import itertools
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from cryptobot.backtest.engine import BacktestEngine  # noqa: E402
from cryptobot.backtest.result import BacktestResult  # noqa: E402
from cryptobot.bot.strategy_selector import STRATEGY_CLASSES  # noqa: E402
from cryptobot.strategies.base import BaseStrategy, StrategyParams  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = str(PROJECT_ROOT / "data" / "cryptobot.db")


def parse_sweep(sweep_str: str) -> dict[str, list[float]]:
    """스윕 문자열을 파싱한다.

    Args:
        sweep_str: "stop_loss_pct=-3,-5,-7 trailing_stop_pct=-2,-3,-5"

    Returns:
        {"stop_loss_pct": [-3.0, -5.0, -7.0], "trailing_stop_pct": [-2.0, -3.0, -5.0]}
    """
    result: dict[str, list[float]] = {}
    for token in sweep_str.split():
        key, values = token.split("=")
        result[key] = [float(v) for v in values.split(",")]
    return result


def create_strategy(strategy_name: str, params_override: dict | None = None) -> BaseStrategy:
    """전략 인스턴스를 생성한다.

    Args:
        strategy_name: 전략 식별자
        params_override: 오버라이드할 파라미터 dict

    Returns:
        전략 인스턴스
    """
    cls = STRATEGY_CLASSES.get(strategy_name)
    if cls is None:
        available = ", ".join(sorted(STRATEGY_CLASSES.keys()))
        raise ValueError(f"알 수 없는 전략: {strategy_name} (가능: {available})")

    params = StrategyParams()
    if params_override:
        for key, value in params_override.items():
            if hasattr(params, key):
                setattr(params, key, value)
            else:
                params.extra[key] = value

    return cls(params)


def format_result_table(results: list[BacktestResult]) -> str:
    """결과를 정렬된 테이블 문자열로 변환한다."""
    if not results:
        return "결과 없음"

    # total_return 내림차순 정렬
    results.sort(key=lambda r: r.total_return_pct, reverse=True)

    cols = ["stop_loss", "trail_stop", "trades", "win_rate", "return%", "max_dd%", "sharpe"]
    header = f"{cols[0]:>10}  {cols[1]:>10}  {cols[2]:>6}  {cols[3]:>8}  {cols[4]:>8}  {cols[5]:>8}  {cols[6]:>7}"
    sep = "-" * len(header)
    lines = [header, sep]

    for r in results:
        stop_loss = r.params.get("stop_loss_pct", "N/A")
        trail_stop = r.params.get("trailing_stop_pct", "N/A")
        lines.append(
            f"{stop_loss:>10}  {trail_stop:>10}  {r.num_trades:>6}  {r.win_rate:>7.1f}%  "
            f"{r.total_return_pct:>+7.1f}%  {r.max_drawdown_pct:>7.1f}%  {r.sharpe_ratio:>7.2f}"
        )

    return "\n".join(lines)


def run_single(strategy_name: str, coin: str, db_path: str) -> BacktestResult:
    """단일 백테스트 실행."""
    strategy = create_strategy(strategy_name)
    engine = BacktestEngine.from_db(db_path, coin, strategy)
    return engine.run()


def run_sweep(
    strategy_name: str, coin: str, db_path: str, sweep_str: str,
) -> list[BacktestResult]:
    """파라미터 스윕 실행."""
    sweep_params = parse_sweep(sweep_str)
    keys = list(sweep_params.keys())
    value_lists = [sweep_params[k] for k in keys]

    results: list[BacktestResult] = []
    combos = list(itertools.product(*value_lists))
    logger.info("스윕 조합 %d개 실행", len(combos))

    for combo in combos:
        override = dict(zip(keys, combo))
        strategy = create_strategy(strategy_name, override)
        engine = BacktestEngine.from_db(db_path, coin, strategy)
        result = engine.run()
        results.append(result)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="백테스트 CLI 러너")
    parser.add_argument("--strategy", required=True, help="전략 이름")
    parser.add_argument("--coin", default="KRW-BTC", help="종목 코드 (기본: KRW-BTC)")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="DB 경로")
    parser.add_argument(
        "--sweep", default=None,
        help='파라미터 스윕 (예: "stop_loss_pct=-3,-5,-7 trailing_stop_pct=-2,-3,-5")',
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="상세 로그 출력")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.sweep:
        results = run_sweep(args.strategy, args.coin, args.db, args.sweep)
    else:
        result = run_single(args.strategy, args.coin, args.db)
        results = [result]

    # 결과 출력
    r0 = results[0]
    print(f"\n=== {r0.strategy_name} / {r0.coin} ({r0.period}) ===\n")
    print(format_result_table(results))

    # 단일 실행 시 거래 상세
    if len(results) == 1 and results[0].num_trades > 0:
        print(f"\n--- 거래 상세 ({results[0].num_trades}건) ---")
        for i, t in enumerate(results[0].trades, 1):
            print(
                f"  {i:>2}. {t.entry_date} → {t.exit_date}  "
                f"{t.entry_price:>12,.0f} → {t.exit_price:>12,.0f}  "
                f"net {t.net_pnl_pct:>+6.2f}%  ({t.hold_days}일)  "
                f"[{t.entry_reason} → {t.exit_reason}]"
            )
    print()


if __name__ == "__main__":
    main()
