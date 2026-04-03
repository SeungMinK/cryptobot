"""테스트용 예제 DB 생성 스크립트.

API Key 없이 Admin 대시보드를 테스트할 수 있도록
시드 데이터가 포함된 SQLite DB를 생성한다.

사용법:
    python scripts/seed_example_db.py

생성 파일:
    data/example/cryptobot.example.db

테스트 계정:
    username: admin
    password: admin1234
"""

import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cryptobot.api.auth import hash_password
from cryptobot.data.database import Database

EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "data" / "example"
EXAMPLE_DB_PATH = EXAMPLE_DIR / "cryptobot.example.db"

# 시드 고정 (재현 가능한 데이터)
random.seed(42)

NOW = datetime(2026, 4, 3, 14, 0, 0)
STRATEGIES = ["volatility_breakout", "ma_crossover", "rsi_mean_reversion", "bollinger_bands", "macd"]
MARKET_STATES = ["bullish", "bearish", "sideways"]
VOLATILITY_LEVELS = ["low", "medium", "high"]


def seed_user(db: Database) -> None:
    """테스트용 admin 계정 생성."""
    pw_hash = hash_password("admin1234")
    db.execute(
        "INSERT INTO users (username, password_hash, display_name, is_admin) VALUES (?, ?, ?, ?)",
        ("admin", pw_hash, "관리자", True),
    )
    db.commit()


def seed_market_snapshots(db: Database) -> None:
    """30일분 시장 스냅샷 데이터 (1시간 간격)."""
    base_price = 75_000_000
    price = base_price

    for hours_ago in range(30 * 24, -1, -1):
        ts = NOW - timedelta(hours=hours_ago)
        change = random.uniform(-0.02, 0.025)
        price = price * (1 + change)
        price = max(price, 60_000_000)

        rsi = 50 + random.uniform(-25, 25)
        ma_5 = price * random.uniform(0.98, 1.02)
        ma_20 = price * random.uniform(0.95, 1.05)
        ma_60 = price * random.uniform(0.92, 1.08)

        if rsi > 60:
            market_state = "bullish"
        elif rsi < 40:
            market_state = "bearish"
        else:
            market_state = "sideways"

        volatility = random.choice(VOLATILITY_LEVELS)

        db.execute(
            """INSERT INTO market_snapshots (
                timestamp, btc_price, btc_open_24h, btc_high_24h, btc_low_24h,
                btc_change_pct_24h, btc_volume_24h, btc_trade_count_24h,
                btc_rsi_14, btc_ma_5, btc_ma_20, btc_ma_60,
                btc_bb_upper, btc_bb_lower, btc_atr_14,
                total_market_volume_krw, top10_avg_change_pct,
                market_state, volatility_level
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                ts.isoformat(),
                round(price),
                round(price * 0.99),
                round(price * 1.02),
                round(price * 0.97),
                round(change * 100, 2),
                round(random.uniform(500_000_000_000, 2_000_000_000_000)),
                random.randint(100_000, 500_000),
                round(rsi, 1),
                round(ma_5),
                round(ma_20),
                round(ma_60),
                round(price * 1.04),
                round(price * 0.96),
                round(price * 0.015),
                round(random.uniform(3_000_000_000_000, 8_000_000_000_000)),
                round(random.uniform(-2, 3), 2),
                market_state,
                volatility,
            ),
        )

    db.commit()


def seed_trades(db: Database) -> None:
    """90건의 매매 데이터 (매수/매도 쌍)."""
    base_price = 72_000_000
    current_price = base_price

    for i in range(45):
        days_ago = random.randint(1, 29)
        hour = random.randint(9, 22)
        buy_ts = NOW - timedelta(days=days_ago, hours=hour)
        sell_ts = buy_ts + timedelta(minutes=random.randint(30, 720))

        strategy = random.choice(STRATEGIES[:3])
        current_price = base_price + random.uniform(-5_000_000, 8_000_000)
        buy_price = round(current_price)
        amount = round(random.uniform(0.0005, 0.005), 8)
        buy_total = round(buy_price * amount)
        buy_fee = round(buy_total * 0.0005)

        market_state = random.choice(MARKET_STATES)
        rsi = round(random.uniform(25, 75), 1)

        # 매수 기록
        db.execute(
            """INSERT INTO trades (
                timestamp, coin, side, price, amount, total_krw, fee_krw,
                strategy, trigger_reason, trigger_value,
                param_k_value, param_stop_loss, param_trailing_stop,
                market_state_at_trade, btc_price_at_trade, rsi_at_trade,
                strategy_params_json, strategy_selection_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                buy_ts.isoformat(),
                "KRW-BTC",
                "buy",
                buy_price,
                amount,
                buy_total,
                buy_fee,
                strategy,
                "buy_signal",
                buy_price,
                round(random.uniform(0.3, 0.7), 2),
                round(random.uniform(-0.05, -0.02), 3),
                round(random.uniform(-0.03, -0.01), 3),
                market_state,
                buy_price,
                rsi,
                json.dumps({"k_value": 0.5}),
                "market_" + market_state,
            ),
        )

        buy_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # 매도 (60% 확률로 수익)
        is_win = random.random() < 0.6
        if is_win:
            profit_pct = round(random.uniform(0.3, 5.0), 2)
        else:
            profit_pct = round(random.uniform(-5.0, -0.2), 2)

        sell_price = round(buy_price * (1 + profit_pct / 100))
        sell_total = round(sell_price * amount)
        sell_fee = round(sell_total * 0.0005)
        profit_krw = round(sell_total - buy_total - buy_fee - sell_fee)
        hold_minutes = int((sell_ts - buy_ts).total_seconds() / 60)

        db.execute(
            """INSERT INTO trades (
                timestamp, coin, side, price, amount, total_krw, fee_krw,
                strategy, trigger_reason, trigger_value,
                param_k_value, param_stop_loss, param_trailing_stop,
                market_state_at_trade, btc_price_at_trade, rsi_at_trade,
                buy_trade_id, profit_pct, profit_krw, hold_duration_minutes,
                strategy_params_json, strategy_selection_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sell_ts.isoformat(),
                "KRW-BTC",
                "sell",
                sell_price,
                amount,
                sell_total,
                sell_fee,
                strategy,
                "sell_signal",
                sell_price,
                round(random.uniform(0.3, 0.7), 2),
                round(random.uniform(-0.05, -0.02), 3),
                round(random.uniform(-0.03, -0.01), 3),
                market_state,
                sell_price,
                rsi,
                buy_id,
                profit_pct,
                profit_krw,
                hold_minutes,
                json.dumps({"k_value": 0.5}),
                "market_" + market_state,
            ),
        )

    db.commit()


def seed_daily_reports(db: Database) -> None:
    """30일분 일일 리포트."""
    balance = 10_000_000
    cumulative = 0.0

    for days_ago in range(29, -1, -1):
        date = (NOW - timedelta(days=days_ago)).date()
        daily_return = round(random.uniform(-2.0, 3.0), 2)
        cumulative += daily_return

        pnl_krw = round(balance * daily_return / 100)
        balance += pnl_krw
        total_asset = balance + round(random.uniform(0, 3_000_000))

        total_trades = random.randint(0, 6)
        buy_trades = total_trades // 2 + total_trades % 2
        sell_trades = total_trades // 2
        winning = random.randint(0, sell_trades) if sell_trades > 0 else 0
        losing = sell_trades - winning

        db.execute(
            """INSERT INTO daily_reports (
                date, starting_balance_krw, ending_balance_krw,
                total_asset_value_krw, realized_pnl_krw, unrealized_pnl_krw,
                daily_return_pct, cumulative_return_pct,
                total_trades, buy_trades, sell_trades,
                winning_trades, losing_trades, win_rate,
                avg_profit_pct, avg_loss_pct, max_drawdown_pct,
                total_fees_krw, market_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                date.isoformat(),
                round(balance - pnl_krw),
                round(balance),
                round(total_asset),
                pnl_krw,
                round(random.uniform(-50000, 100000)),
                daily_return,
                round(cumulative, 2),
                total_trades,
                buy_trades,
                sell_trades,
                winning,
                losing,
                round(winning / sell_trades * 100, 1) if sell_trades > 0 else 0,
                round(random.uniform(0.5, 3.0), 2),
                round(random.uniform(-3.0, -0.5), 2),
                round(random.uniform(-5.0, -0.5), 2),
                round(random.uniform(100, 2000)),
                random.choice(MARKET_STATES),
            ),
        )

    db.commit()


def seed_strategy_activations(db: Database) -> None:
    """전략 활성화 이력."""
    activations = [
        (NOW - timedelta(days=25), "volatility_breakout", "activate", "manual", "bullish", "초기 전략 설정"),
        (NOW - timedelta(days=20), "ma_crossover", "activate", "llm", "bullish", "추세 전환 감지"),
        (NOW - timedelta(days=15), "ma_crossover", "deactivate", "manual", "sideways", "횡보장 전환"),
        (NOW - timedelta(days=15), "rsi_mean_reversion", "activate", "llm", "sideways", "횡보장 전략 전환"),
        (NOW - timedelta(days=7), "rsi_mean_reversion", "deactivate", "manual", "bullish", "상승장 전환"),
        (NOW - timedelta(days=7), "volatility_breakout", "activate", "manual", "bullish", "변동성 돌파 재활성화"),
    ]

    for ts, name, action, source, state, reason in activations:
        db.execute(
            """INSERT INTO strategy_activations (
                timestamp, strategy_name, action, source, market_state, reason
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (ts.isoformat(), name, action, source, state, reason),
        )

    db.commit()


def main() -> None:
    # 기존 파일 삭제
    EXAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    if EXAMPLE_DB_PATH.exists():
        EXAMPLE_DB_PATH.unlink()

    db = Database(EXAMPLE_DB_PATH)
    db.initialize()

    print("시드 데이터 생성 중...")
    seed_user(db)
    print("  - admin 계정 생성 (admin / admin1234)")

    seed_market_snapshots(db)
    count = db.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
    print(f"  - 시장 스냅샷: {count}건")

    seed_trades(db)
    count = db.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
    print(f"  - 매매 내역: {count}건")

    seed_daily_reports(db)
    count = db.execute("SELECT COUNT(*) FROM daily_reports").fetchone()[0]
    print(f"  - 일일 리포트: {count}건")

    seed_strategy_activations(db)
    count = db.execute("SELECT COUNT(*) FROM strategy_activations").fetchone()[0]
    print(f"  - 전략 활성화 이력: {count}건")

    strategies_count = db.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
    print(f"  - 전략: {strategies_count}건")

    db.close()

    print(f"\n예제 DB 생성 완료: {EXAMPLE_DB_PATH}")
    print("\n테스트 방법:")
    print("  1. cp data/example/cryptobot.example.db data/cryptobot.db")
    print("  2. uvicorn cryptobot.api.main:app --reload --port 8000")
    print("  3. cd admin && npm run dev")
    print("  4. http://localhost:5173 접속 → admin / admin1234 로그인")


if __name__ == "__main__":
    main()
