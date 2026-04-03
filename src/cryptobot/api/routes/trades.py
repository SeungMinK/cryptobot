"""매매 내역 라우트.

NestJS의 TradeController와 동일.
"""

from fastapi import APIRouter, Depends, Query

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("")
def get_trades(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    coin: str | None = None,
    strategy: str | None = None,
    side: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    _: UserResponse = Depends(get_current_user),
):
    """매매 내역 조회 (페이지네이션 + 필터)."""
    db = get_db()
    conditions = []
    params = []

    if coin:
        conditions.append("coin = ?")
        params.append(coin)
    if strategy:
        conditions.append("strategy = ?")
        params.append(strategy)
    if side:
        conditions.append("side = ?")
        params.append(side)
    if date_from:
        conditions.append("DATE(timestamp) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("DATE(timestamp) <= ?")
        params.append(date_to)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * limit

    # 총 개수
    total = db.execute(f"SELECT COUNT(*) FROM trades {where}", tuple(params)).fetchone()[0]

    # 데이터
    rows = db.execute(
        f"SELECT * FROM trades {where} ORDER BY id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/stats")
def get_trade_stats(
    days: int = Query(7, ge=1, le=365),
    _: UserResponse = Depends(get_current_user),
):
    """매매 통계."""
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) as total_trades,
            SUM(CASE WHEN side='buy' THEN 1 ELSE 0 END) as buys,
            SUM(CASE WHEN side='sell' THEN 1 ELSE 0 END) as sells,
            SUM(CASE WHEN side='sell' AND profit_pct > 0 THEN 1 ELSE 0 END) as wins,
            SUM(CASE WHEN side='sell' AND profit_pct <= 0 THEN 1 ELSE 0 END) as losses,
            AVG(CASE WHEN side='sell' THEN profit_pct END) as avg_profit_pct,
            SUM(CASE WHEN side='sell' THEN profit_krw ELSE 0 END) as total_profit_krw,
            SUM(fee_krw) as total_fees
        FROM trades
        WHERE timestamp >= datetime('now', ?)
        """,
        (f"-{days} days",),
    ).fetchone()

    sells = (row["wins"] or 0) + (row["losses"] or 0)
    return {
        "period_days": days,
        "total_trades": row["total_trades"] or 0,
        "buys": row["buys"] or 0,
        "sells": sells,
        "wins": row["wins"] or 0,
        "losses": row["losses"] or 0,
        "win_rate": round((row["wins"] or 0) / sells * 100, 1) if sells > 0 else 0,
        "avg_profit_pct": round(row["avg_profit_pct"] or 0, 2),
        "total_profit_krw": round(row["total_profit_krw"] or 0, 0),
        "total_fees": round(row["total_fees"] or 0, 0),
    }


@router.get("/daily")
def get_daily_returns(
    days: int = Query(30, ge=1, le=365),
    _: UserResponse = Depends(get_current_user),
):
    """일별 수익률."""
    db = get_db()
    rows = db.execute(
        """
        SELECT
            DATE(timestamp) as date,
            SUM(CASE WHEN side='sell' THEN profit_pct ELSE 0 END) as daily_pnl_pct,
            SUM(CASE WHEN side='sell' THEN profit_krw ELSE 0 END) as daily_pnl_krw,
            COUNT(*) as trade_count
        FROM trades
        WHERE timestamp >= datetime('now', ?)
        GROUP BY DATE(timestamp)
        ORDER BY date
        """,
        (f"-{days} days",),
    ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{trade_id}")
def get_trade_detail(trade_id: int, _: UserResponse = Depends(get_current_user)):
    """매매 상세 조회."""
    db = get_db()
    row = db.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
    if row is None:
        return {"detail": "매매 내역을 찾을 수 없습니다"}
    return dict(row)
