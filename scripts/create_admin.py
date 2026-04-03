"""Admin 계정 생성 스크립트.

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

    db = Database(config.bot.db_path)
    db.initialize()

    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        pw_hash = hash_password(password)
        db.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username))
        db.commit()
        print(f"기존 계정 '{username}' 비밀번호 변경 완료")
    else:
        pw_hash = hash_password(password)
        db.execute(
            "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, ?)",
            (username, pw_hash, "관리자", True),
        )
        db.commit()
        print(f"Admin 계정 생성 완료: {username}")

    db.close()


if __name__ == "__main__":
    main()
