"""Slack 알림 모듈.

Bot Token 방식(권장)과 Webhook 방식을 모두 지원한다.
SLACK_BOT_TOKEN + SLACK_CHANNEL이 설정되어 있으면 Bot Token 방식을 우선 사용하고,
없으면 SLACK_WEBHOOK_URL로 폴백한다.
"""

import json
import logging

import requests

from cryptobot.bot.config import config

logger = logging.getLogger(__name__)


class SlackNotifier:
    """Slack 알림 전송기.

    Bot Token 방식(slack_sdk)을 우선 사용하고,
    미설정 시 Webhook 방식으로 폴백한다.
    """

    def __init__(self) -> None:
        self._bot_token = config.slack.bot_token
        self._channel = config.slack.channel
        self._webhook_url = config.slack.webhook_url
        self._client = None

        if self._bot_token and self._channel:
            try:
                from slack_sdk import WebClient

                self._client = WebClient(token=self._bot_token)
                logger.info("Slack Bot Token 방식 초기화 완료 (채널: %s)", self._channel)
            except ImportError:
                logger.warning("slack_sdk 미설치 — pip install slack_sdk 필요. Webhook으로 폴백합니다.")
        elif self._webhook_url:
            logger.info("Slack Webhook 방식 초기화 (deprecated)")
        else:
            logger.info("Slack 미설정 — 알림 비활성화")

    @property
    def is_configured(self) -> bool:
        """Slack 알림 전송 가능 여부."""
        return self._client is not None or bool(self._webhook_url)

    def send(self, text: str) -> bool:
        """텍스트 메시지 전송.

        Args:
            text: 전송할 메시지 (Slack mrkdwn 형식)

        Returns:
            전송 성공 여부
        """
        if not self.is_configured:
            logger.debug("Slack 미설정 — 메시지 스킵: %s", text[:50])
            return False

        # Bot Token 방식 우선
        if self._client is not None:
            return self._send_bot_token(text)

        # Webhook 폴백
        return self._send_webhook(text)

    def _send_bot_token(self, text: str) -> bool:
        """Bot Token 방식으로 메시지 전송."""
        try:
            response = self._client.chat_postMessage(
                channel=self._channel,
                text=text,
                mrkdwn=True,
            )
            if response["ok"]:
                logger.debug("Slack 전송 성공 (Bot Token)")
                return True
            else:
                logger.warning("Slack 전송 실패: %s", response.get("error", "unknown"))
                return False
        except Exception as e:
            logger.error("Slack Bot Token 전송 에러: %s", e)
            return False

    def _send_webhook(self, text: str) -> bool:
        """[DEPRECATED] Webhook 방식으로 메시지 전송."""
        try:
            response = requests.post(
                self._webhook_url,
                data=json.dumps({"text": text}),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning("Slack Webhook 전송 실패: %d %s", response.status_code, response.text)
                return False
            return True
        except requests.RequestException as e:
            logger.error("Slack Webhook 전송 에러: %s", e)
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

    def notify_tick_report(
        self,
        strategy_name: str,
        signal_type: str,
        confidence: float,
        reason: str,
        current_price: float,
        market_state: str,
        indicators: dict,
    ) -> bool:
        """틱별 판단 리포트 — 매수/매도/HOLD 근거 상세 발송."""
        signal_emoji = {"buy": "🟢 매수", "sell": "🔴 매도"}.get(signal_type, "⏸️ HOLD")
        confidence_bar = "█" * int(confidence * 10) + "░" * (10 - int(confidence * 10))

        indicator_lines = []
        if indicators.get("rsi_14") is not None:
            indicator_lines.append(f"• RSI(14): {indicators['rsi_14']:.1f}")
        if indicators.get("ma_5") is not None and indicators.get("ma_20") is not None:
            indicator_lines.append(f"• MA(5/20): {indicators['ma_5']:,.0f} / {indicators['ma_20']:,.0f}")
        if indicators.get("bb_upper") is not None and indicators.get("bb_lower") is not None:
            indicator_lines.append(f"• 볼린저: {indicators['bb_lower']:,.0f} ~ {indicators['bb_upper']:,.0f}")
        if indicators.get("atr_14") is not None:
            indicator_lines.append(f"• ATR(14): {indicators['atr_14']:,.0f}")
        indicator_text = "\n".join(indicator_lines) if indicator_lines else "• 지표 데이터 없음"

        text = (
            f"{signal_emoji} *틱 리포트*\n"
            f"• 전략: {strategy_name}\n"
            f"• 판단: {reason}\n"
            f"• 신뢰도: [{confidence_bar}] {confidence:.1%}\n"
            f"• BTC: {current_price:,.0f}원\n"
            f"• 시장: {market_state}\n"
            f"─── 지표 ───\n"
            f"{indicator_text}"
        )
        return self.send(text)

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
