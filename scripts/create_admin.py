"""Admin 유저 생성 스크립트.

사용법:
    python scripts/create_admin.py <username> <password>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.api.auth import hash_password
from cryptobot.bot.config import config
from cryptobot.data.database import Database


def main() -> None:
    if len(sys.argv) < 3:
        print("사용법: python scripts/create_admin.py <username> <password>")
        sys.exit(1)

    username = sys.argv[1]
    password = sys.argv[2]

    with Database(config.bot.db_path) as db:
        db.initialize()

        # 이미 존재하는지 확인
        existing = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            print(f"이미 존재하는 유저: {username}")
            sys.exit(1)

        password_hash = hash_password(password)
        db.execute(
            "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, ?)",
            (username, password_hash, username, True),
        )
        db.commit()
        print(f"Admin 유저 생성 완료: {username}")


if __name__ == "__main__":
    main()
