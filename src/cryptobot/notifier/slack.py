"""Slack 알림 모듈.

Webhook을 통해 매매 알림, 에러 알림, 일일 리포트를 전송한다.
"""

import json
import logging

import requests

from cryptobot.bot.config import config

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Slack Webhook 알림 전송기."""

    def __init__(self) -> None:
        self._webhook_url = config.slack.webhook_url

    @property
    def is_configured(self) -> bool:
        return bool(self._webhook_url)

    def send(self, text: str) -> bool:
        """텍스트 메시지 전송.

        Returns:
            전송 성공 여부
        """
        if not self.is_configured:
            logger.debug("Slack 미설정 — 메시지 스킵: %s", text[:50])
            return False

        try:
            response = requests.post(
                self._webhook_url,
                data=json.dumps({"text": text}),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning("Slack 전송 실패: %d %s", response.status_code, response.text)
                return False
            return True
        except requests.RequestException as e:
            logger.error("Slack 전송 에러: %s", e)
            return False

    def notify_trade(self, side: str, coin: str, price: float, amount: float, total_krw: float) -> bool:
        """매매 체결 알림."""
        emoji = "🟢" if side == "buy" else "🔴"
        side_kr = "매수" if side == "buy" else "매도"
        text = (
            f"{emoji} *{side_kr} 체결*\n"
            f"• 종목: {coin}\n"
            f"• 가격: {price:,.0f}원\n"
            f"• 수량: {amount:.8f}\n"
            f"• 금액: {total_krw:,.0f}원"
        )
        return self.send(text)

    def notify_profit(self, coin: str, profit_pct: float, profit_krw: float, hold_minutes: int) -> bool:
        """매도 시 수익/손실 알림."""
        emoji = "💰" if profit_pct > 0 else "💸"
        text = (
            f"{emoji} *매매 결과*\n"
            f"• 종목: {coin}\n"
            f"• 수익률: {profit_pct:+.2f}%\n"
            f"• 수익금: {profit_krw:+,.0f}원\n"
            f"• 보유시간: {hold_minutes}분"
        )
        return self.send(text)

    def notify_error(self, error_msg: str) -> bool:
        """에러 알림."""
        return self.send(f"⚠️ *에러 발생*\n```{error_msg}```")

    def notify_bot_status(self, status: str) -> bool:
        """봇 시작/종료 알림."""
        return self.send(f"🤖 *봇 상태*: {status}")

    def notify_daily_report(
        self,
        date_str: str,
        daily_return_pct: float,
        total_trades: int,
        win_rate: float,
        balance_krw: float,
    ) -> bool:
        """일일 정산 리포트."""
        emoji = "📈" if daily_return_pct >= 0 else "📉"
        text = (
            f"{emoji} *일일 리포트 ({date_str})*\n"
            f"• 수익률: {daily_return_pct:+.2f}%\n"
            f"• 거래: {total_trades}건\n"
            f"• 승률: {win_rate:.0f}%\n"
            f"• 잔고: {balance_krw:,.0f}원"
        )
        return self.send(text)
