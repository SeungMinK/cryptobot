"""수동 매수/매도 테스트 스크립트.

5,000원어치 BTC를 시장가 매수 → 10초 대기 → 전량 시장가 매도.
실제 주문이 체결되므로 주의!

사용법:
    python scripts/test_trade.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.bot.config import config
from cryptobot.bot.trader import Trader
from cryptobot.notifier.slack import SlackNotifier


def main() -> None:
    trader = Trader()
    notifier = SlackNotifier()

    if not trader.is_ready:
        print("업비트 API Key 미설정. .env 확인하세요.")
        sys.exit(1)

    coin = config.bot.coin
    amount_krw = 5000

    # 잔고 확인
    krw = trader.get_balance_krw()
    print(f"현재 KRW 잔고: {krw:,.0f}원")

    if krw < amount_krw:
        print(f"잔고 부족. 최소 {amount_krw:,}원 필요.")
        sys.exit(1)

    # 현재가 확인
    price = trader.get_current_price(coin)
    print(f"{coin} 현재가: {price:,.0f}원")

    confirm = input(f"\n{amount_krw:,}원어치 {coin} 매수 → 매도 테스트를 실행합니다. 계속? (y/n): ").strip()
    if confirm.lower() != "y":
        print("취소됨.")
        return

    # 1. 시장가 매수
    print(f"\n[1/3] {amount_krw:,}원 시장가 매수 중...")
    buy_result = trader.buy_market(coin, amount_krw)

    if not buy_result.success:
        print(f"매수 실패: {buy_result.error}")
        sys.exit(1)

    print(f"매수 완료! 가격={buy_result.price:,.0f}원, 수량={buy_result.amount:.8f}")
    notifier.send(f"🧪 *테스트 매수*\n• {coin} {buy_result.amount:.8f}개\n• {amount_krw:,}원")

    # 2. 대기
    print("\n[2/3] 10초 대기...")
    time.sleep(10)

    # 3. 전량 시장가 매도
    coin_balance = trader.get_balance_coin(coin)
    print(f"\n[3/3] 전량 시장가 매도 중... (보유: {coin_balance:.8f})")

    if coin_balance <= 0:
        print("보유 코인 없음. 매도 스킵.")
        return

    sell_result = trader.sell_market(coin, coin_balance)

    if not sell_result.success:
        print(f"매도 실패: {sell_result.error}")
        sys.exit(1)

    print(f"매도 완료! 가격={sell_result.price:,.0f}원")

    # 결과 요약
    profit_krw = sell_result.total_krw - buy_result.total_krw - buy_result.fee_krw - sell_result.fee_krw
    profit_pct = (sell_result.price - buy_result.price) / buy_result.price * 100
    final_krw = trader.get_balance_krw()

    print(f"\n===== 테스트 결과 =====")
    print(f"매수: {buy_result.total_krw:,.0f}원 (수수료 {buy_result.fee_krw:,.0f}원)")
    print(f"매도: {sell_result.total_krw:,.0f}원 (수수료 {sell_result.fee_krw:,.0f}원)")
    print(f"손익: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)")
    print(f"최종 잔고: {final_krw:,.0f}원")

    notifier.send(
        f"🧪 *테스트 완료*\n"
        f"• 매수: {buy_result.total_krw:,.0f}원 → 매도: {sell_result.total_krw:,.0f}원\n"
        f"• 손익: {profit_krw:+,.0f}원 ({profit_pct:+.2f}%)\n"
        f"• 최종 잔고: {final_krw:,.0f}원"
    )

    print("\n테스트 성공! 봇이 정상 동작합니다.")
    print("이제 봇을 실행하세요: python -m cryptobot")


if __name__ == "__main__":
    main()
