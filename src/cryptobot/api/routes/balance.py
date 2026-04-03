"""잔고 + 포지션 라우트."""

from fastapi import APIRouter, Depends, Query

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db, get_recorder

router = APIRouter(prefix="/api/balance", tags=["balance"])


@router.get("")
def get_balance(_: UserResponse = Depends(get_current_user)):
    """현재 잔고 + 보유 포지션."""
    from cryptobot.bot.config import config
    from cryptobot.bot.trader import Trader

    trader = Trader()
    result = {"krw_balance": 0, "coin_balance": 0, "coin_value_krw": 0, "total_asset_krw": 0, "api_connected": False}

    if trader.is_ready:
        try:
            result["api_connected"] = True
            result["krw_balance"] = trader.get_balance_krw()
            result["coin_balance"] = trader.get_balance_coin(config.bot.coin)
            price = trader.get_current_price(config.bot.coin)
            result["coin_value_krw"] = result["coin_balance"] * price
            result["total_asset_krw"] = result["krw_balance"] + result["coin_value_krw"]
        except Exception:
            pass

    return result


@router.get("/positions")
def get_positions(_: UserResponse = Depends(get_current_user)):
    """현재 보유 포지션 (미실현 손익 포함)."""
    from cryptobot.bot.config import config
    from cryptobot.bot.trader import Trader

    recorder = get_recorder()
    active_trade = recorder.get_active_buy_trade(config.bot.coin)

    if active_trade is None:
        return {"has_position": False, "position": None}

    # 현재가 조회
    try:
        current_price = Trader().get_current_price(config.bot.coin)
        unrealized_pnl_pct = (current_price - active_trade["price"]) / active_trade["price"] * 100
        unrealized_pnl_krw = (current_price - active_trade["price"]) * active_trade["amount"]
    except Exception:
        current_price = 0
        unrealized_pnl_pct = 0
        unrealized_pnl_krw = 0

    return {
        "has_position": True,
        "position": {
            **dict(active_trade),
            "current_price": current_price,
            "unrealized_pnl_pct": round(unrealized_pnl_pct, 2),
            "unrealized_pnl_krw": round(unrealized_pnl_krw, 0),
        },
    }


@router.get("/history")
def get_balance_history(
    days: int = Query(30, ge=1, le=365),
    _: UserResponse = Depends(get_current_user),
):
    """자산 추이 (daily_reports 기반)."""
    db = get_db()
    rows = db.execute(
        """
        SELECT date, ending_balance_krw, total_asset_value_krw,
               daily_return_pct, cumulative_return_pct
        FROM daily_reports
        WHERE date >= date('now', ?)
        ORDER BY date
        """,
        (f"-{days} days",),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/history/snapshots")
def get_balance_history_snapshots(
    hours: int = Query(1, ge=1, le=720),
    _: UserResponse = Depends(get_current_user),
):
    """시간 기반 자산 추이 (market_snapshots 기반).

    1시간~30일까지 지원. 데이터 포인트는 최대 200개로 제한.
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT timestamp, btc_price, market_state
        FROM market_snapshots
        WHERE timestamp >= datetime('now', ?)
        ORDER BY timestamp
        """,
        (f"-{hours} hours",),
    ).fetchall()

    if not rows:
        return []

    # 데이터 포인트가 너무 많으면 샘플링
    data = [dict(r) for r in rows]
    if len(data) > 200:
        step = len(data) // 200
        data = data[::step] + [data[-1]]

    return data
