"""Admin 계정 생성 스크립트.

사용법:
    python scripts/create_admin.py

대화형으로 username/password를 입력받는다.
(쉘 특수문자 문제 방지를 위해 인자 대신 input 사용)
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.api.auth import hash_password, verify_password
from cryptobot.bot.config import config
from cryptobot.data.database import Database


def main() -> None:
    username = input("Username: ").strip()
    if not username:
        print("Username을 입력하세요.")
        sys.exit(1)

    password = getpass.getpass("Password: ")
    if not password:
        print("Password를 입력하세요.")
        sys.exit(1)

    db = Database(config.bot.db_path)
    db.initialize()

    pw_hash = hash_password(password)

    row = db.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if row:
        db.execute("UPDATE users SET password_hash = ? WHERE username = ?", (pw_hash, username))
        db.commit()
        print(f"기존 계정 '{username}' 비밀번호 변경 완료")
    else:
        db.execute(
            "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, ?)",
            (username, pw_hash, "관리자", True),
        )
        db.commit()
        print(f"Admin 계정 생성 완료: {username}")

    # 검증
    row = db.execute("SELECT password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if verify_password(password, row["password_hash"]):
        print("비밀번호 검증: OK")
    else:
        print("ERROR: 비밀번호 검증 실패!")

    db.close()


if __name__ == "__main__":
    main()
