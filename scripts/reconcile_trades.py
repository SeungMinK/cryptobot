"""기존 거래 일괄 보정 스크립트.

order_uuid 없는 기존 거래는 보정 불가 → 현재 오차를 로그로 기록.
order_uuid 있는 거래는 업비트 API로 실체결가 확인 후 보정.

사용법:
    python -m scripts.reconcile_trades
"""

import logging
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cryptobot.bot.config import config
from cryptobot.bot.health_checker import HealthChecker
from cryptobot.bot.trader import Trader
from cryptobot.data.database import Database
from cryptobot.logging_config import setup_logging

setup_logging("reconcile", "INFO")
logger = logging.getLogger(__name__)


def main() -> None:
    """기존 거래 정합성 보정 실행."""
    db = Database(config.bot.db_path)
    db.initialize()

    # 전체 거래 통계
    total = db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    with_uuid = db.execute("SELECT COUNT(*) FROM trades WHERE order_uuid IS NOT NULL").fetchone()[0]
    without_uuid = db.execute("SELECT COUNT(*) FROM trades WHERE order_uuid IS NULL").fetchone()[0]
    already_reconciled = db.execute("SELECT COUNT(*) FROM trades WHERE reconciled > 0").fetchone()[0]

    logger.info("=== 거래 정합성 보정 시작 ===")
    logger.info("전체 거래: %d건", total)
    logger.info("  - order_uuid 있음: %d건 (보정 가능)", with_uuid)
    logger.info("  - order_uuid 없음: %d건 (보정 불가)", without_uuid)
    logger.info("  - 이미 검증됨: %d건", already_reconciled)

    if without_uuid > 0:
        # 보정 불가 거래의 오차 추정
        row = db.execute(
            """
            SELECT
                SUM(CASE WHEN side = 'sell' THEN profit_krw ELSE 0 END) as total_profit
            FROM trades
            WHERE order_uuid IS NULL AND side = 'sell' AND profit_krw IS NOT NULL
            """
        ).fetchone()
        estimated_profit = row[0] if row and row[0] else 0
        logger.info("보정 불가 거래의 DB 기록 기준 누적 수익: %.0f원 (실제와 차이 있을 수 있음)", estimated_profit)

    # order_uuid가 있는 미검증 거래 보정
    trader = Trader()
    if not trader.is_ready:
        logger.error("업비트 API Key 미설정 — 보정 불가")
        db.close()
        return

    checker = HealthChecker(db, trader)
    result = checker.reconcile_trades()
    logger.info("보정 결과: %s", result)

    db.close()
    logger.info("=== 거래 정합성 보정 완료 ===")


if __name__ == "__main__":
    main()
