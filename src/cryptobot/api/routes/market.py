"""시장 현황 라우트."""

from fastapi import APIRouter, Depends, Query

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/current")
def get_current_market(_: UserResponse = Depends(get_current_user)):
    """현재 시장 상태 (최근 스냅샷 기반)."""
    db = get_db()
    row = db.execute("SELECT * FROM market_snapshots ORDER BY id DESC LIMIT 1").fetchone()

    if row is None:
        return {"status": "no_data", "message": "시장 데이터 없음"}

    return dict(row)


@router.get("/snapshots")
def get_snapshots(
    limit: int = Query(60, ge=1, le=1440),
    _: UserResponse = Depends(get_current_user),
):
    """최근 스냅샷 이력."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM market_snapshots ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


@router.get("/signals")
def get_recent_signals(
    limit: int = Query(50, ge=1, le=200),
    _: UserResponse = Depends(get_current_user),
):
    """최근 매매 신호."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM trade_signals ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]
