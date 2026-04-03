"""데이터베이스 초기화 스크립트.

사용법:
    python scripts/setup_db.py
"""

import sys
from pathlib import Path

# 프로젝트 루트의 src를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.bot.config import config
from cryptobot.data.database import Database


def main() -> None:
    with Database(config.bot.db_path) as db:
        db.initialize()
        print(f"DB 초기화 완료: {config.bot.db_path}")

        # 테이블 목록 출력
        tables = db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        print(f"생성된 테이블 ({len(tables)}개):")
        for table in tables:
            count = db.execute(f"SELECT COUNT(*) FROM {table['name']}").fetchone()[0]
            print(f"  - {table['name']} ({count}행)")


if __name__ == "__main__":
    main()
