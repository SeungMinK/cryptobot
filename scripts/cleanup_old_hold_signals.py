"""오래된 hold 신호 정리 — DB 부피/조회 성능 개선.

실측: trade_signals가 시간당 수천 건 쌓여 테이블이 거대화됨. buy/sell은 영구 보존해야 하나
hold는 조건 미충족 기록용이라 14일 이상이면 삭제해도 무방.

사용법:
    python -m cryptobot.scripts.cleanup_old_hold_signals           # 14일 이전 hold 삭제
    python -m cryptobot.scripts.cleanup_old_hold_signals --days 7  # 기간 지정
    python -m cryptobot.scripts.cleanup_old_hold_signals --dry-run # 삭제할 건수만 출력

APScheduler 주간 잡으로도 호출 가능 (main.py에서 scheduler.add_job 참조).
"""

import argparse
import logging

from cryptobot.bot.config import config
from cryptobot.data.database import Database

logger = logging.getLogger(__name__)


def cleanup(days: int = 14, dry_run: bool = False) -> int:
    """days일 이전의 hold 신호 삭제. 삭제 건수 반환."""
    db = Database(config.bot.db_path)
    db.initialize()
    try:
        row = db.execute(
            "SELECT COUNT(*) FROM trade_signals "
            "WHERE signal_type = 'hold' AND timestamp < datetime('now', ?)",
            (f"-{days} days",),
        ).fetchone()
        count = row[0] if row else 0

        if count == 0:
            print(f"[cleanup] {days}일 이전 hold 신호 없음")
            return 0

        if dry_run:
            print(f"[dry-run] {days}일 이전 hold 신호 {count:,}건 — 실제 삭제 안 함")
            return count

        db.execute(
            "DELETE FROM trade_signals "
            "WHERE signal_type = 'hold' AND timestamp < datetime('now', ?)",
            (f"-{days} days",),
        )
        db.commit()
        db.execute("VACUUM")
        print(f"[cleanup] hold 신호 {count:,}건 삭제 + VACUUM 완료")
        return count
    finally:
        db.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=14, help="N일 이전 데이터 삭제 (기본 14)")
    parser.add_argument("--dry-run", action="store_true", help="삭제하지 않고 건수만 출력")
    args = parser.parse_args()
    cleanup(days=args.days, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
