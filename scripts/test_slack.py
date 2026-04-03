"""Slack 알림 테스트 스크립트.

사용법:
    python scripts/test_slack.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.notifier.slack import SlackNotifier


def main() -> None:
    notifier = SlackNotifier()

    if not notifier.is_configured:
        print("Slack 미설정. .env 파일에 SLACK_BOT_TOKEN + SLACK_CHANNEL을 설정하세요.")
        sys.exit(1)

    print("테스트 메시지 전송 중...")
    result = notifier.send("🧪 *CryptoBot 테스트*\nSlack 연동이 정상적으로 동작합니다!")

    if result:
        print("전송 성공!")
    else:
        print("전송 실패. 토큰과 채널 설정을 확인하세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
