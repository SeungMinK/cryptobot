"""뉴스 라우트."""

from fastapi import APIRouter, Depends, Query

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/news", tags=["news"])


@router.get("")
def get_news(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    source: str | None = Query(None),
    category: str | None = Query(None),
    sentiment: str | None = Query(None),
    coin: str | None = Query(None),
    _: UserResponse = Depends(get_current_user),
):
    """뉴스 목록 조회."""
    db = get_db()
    conditions = []
    params: list = []

    if source:
        conditions.append("source = ?")
        params.append(source)
    if category:
        conditions.append("category = ?")
        params.append(category)
    if sentiment:
        conditions.append("sentiment_keyword = ?")
        params.append(sentiment)
    if coin:
        conditions.append("coins_mentioned LIKE ?")
        params.append(f"%{coin}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (page - 1) * limit

    total = db.execute(f"SELECT COUNT(*) FROM news_articles {where}", tuple(params)).fetchone()[0]
    rows = db.execute(
        f"SELECT * FROM news_articles {where} ORDER BY published_at DESC, id DESC LIMIT ? OFFSET ?",
        (*params, limit, offset),
    ).fetchall()

    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/stats")
def get_news_stats(
    hours: int = Query(24, ge=1, le=720),
    _: UserResponse = Depends(get_current_user),
):
    """뉴스 통계."""
    db = get_db()
    row = db.execute(
        """
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN sentiment_keyword = 'positive' THEN 1 ELSE 0 END) as positive,
            SUM(CASE WHEN sentiment_keyword = 'negative' THEN 1 ELSE 0 END) as negative,
            SUM(CASE WHEN sentiment_keyword = 'neutral' THEN 1 ELSE 0 END) as neutral,
            SUM(CASE WHEN coins_mentioned != '' THEN 1 ELSE 0 END) as coin_tagged
        FROM news_articles
        WHERE collected_at >= datetime('now', ?)
        """,
        (f"-{hours} hours",),
    ).fetchone()

    # Fear & Greed 최신
    fg = db.execute("SELECT * FROM fear_greed_index ORDER BY id DESC LIMIT 1").fetchone()

    return {
        **dict(row),
        "fear_greed": dict(fg) if fg else None,
    }
