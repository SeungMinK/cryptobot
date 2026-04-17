"""매매 신호 라우트."""

from fastapi import APIRouter, Depends, Query

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
def get_signals(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    signal_type: str | None = Query(None),
    strategy: str | None = Query(None),
    exclude_hold: bool = Query(False, description="hold 신호 제외"),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0, description="신뢰도 최소값 (0.0~1.0)"),
    _: UserResponse = Depends(get_current_user),
):
    """매매 신호 목록 조회 (최신순).

    hold 신호는 조건 미충족 기록용이라 confidence=0인 것이 정상이므로,
    대시보드 기본 뷰에서는 exclude_hold=true 권장.
    """
    db = get_db()

    where_clauses = []
    params: list = []

    if signal_type:
        where_clauses.append("signal_type = ?")
        params.append(signal_type)
    if exclude_hold:
        where_clauses.append("signal_type != 'hold'")
    if min_confidence is not None:
        where_clauses.append("confidence >= ?")
        params.append(min_confidence)
    if strategy:
        where_clauses.append("strategy = ?")
        params.append(strategy)

    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    # 전체 개수
    total = db.execute(f"SELECT COUNT(*) FROM trade_signals {where}", tuple(params)).fetchone()[0]

    # 페이지네이션
    offset = (page - 1) * limit
    rows = db.execute(
        f"""
        SELECT ts.*, ms.rsi_14, ms.ma_5, ms.ma_20,
               ms.bb_upper, ms.bb_lower, ms.atr_14, ms.market_state
        FROM trade_signals ts
        LEFT JOIN market_snapshots ms ON ts.snapshot_id = ms.id
        {where}
        ORDER BY ts.id DESC
        LIMIT ? OFFSET ?
        """,
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
def get_signal_stats(
    hours: int = Query(1, ge=1, le=720),
    _: UserResponse = Depends(get_current_user),
):
    """신호 통계 (기간별)."""
    db = get_db()

    row = db.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN signal_type = 'buy' THEN 1 ELSE 0 END) as buy_signals,
            SUM(CASE WHEN signal_type = 'sell' THEN 1 ELSE 0 END) as sell_signals,
            SUM(CASE WHEN signal_type = 'hold' THEN 1 ELSE 0 END) as hold_signals,
            SUM(CASE WHEN executed = TRUE THEN 1 ELSE 0 END) as executed,
            AVG(CASE WHEN signal_type = 'buy' THEN confidence END) as avg_buy_confidence,
            AVG(current_price) as avg_price
        FROM trade_signals
        WHERE timestamp >= datetime('now', ?)
        """,
        (f"-{hours} hours",),
    ).fetchone()

    return dict(row) if row else {}
