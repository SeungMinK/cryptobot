"""시장 현황 라우트."""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

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


class CoinScanRequest(BaseModel):
    max_coins: int = 5
    min_volume_krw: float = 1_000_000_000
    min_price_krw: float = 1_000


@router.post("/scan-preview")
def scan_coins_preview(body: CoinScanRequest, _: UserResponse = Depends(get_current_user)):
    """코인 선별 미리보기. 필터 조건을 바꿔서 어떤 코인이 선별되는지 확인."""
    from cryptobot.bot.scanner import CoinScanner

    scanner = CoinScanner(
        min_volume_krw=body.min_volume_krw,
        min_price_krw=body.min_price_krw,
        max_coins=body.max_coins,
    )
    return scanner.scan_top_coins()


@router.get("/scan-current")
def scan_coins_current(_: UserResponse = Depends(get_current_user)):
    """현재 설정 기준 코인 선별 결과."""
    from cryptobot.bot.scanner import CoinScanner

    db = get_db()

    def _get(key: str, default: str) -> str:
        row = db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    scanner = CoinScanner(
        min_volume_krw=float(_get("min_volume_krw", "1000000000")),
        min_price_krw=float(_get("min_price_krw", "1000")),
        max_coins=int(_get("max_coins", "5")),
    )
    return scanner.scan_top_coins()
