"""코인 카테고리별 전략 설정 라우트."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/coin-strategy", tags=["coin-strategy"])


class CoinStrategyResponse(BaseModel):
    id: int
    category: str
    strategy_name: str
    stop_loss_pct: float
    trailing_stop_pct: float
    position_size_pct: float
    strategy_params_json: str | None
    description: str | None
    updated_at: str


class CoinStrategyUpdate(BaseModel):
    strategy_name: str
    stop_loss_pct: float
    trailing_stop_pct: float
    position_size_pct: float
    strategy_params_json: str | None = None


@router.get("")
def get_all_coin_strategies(_: UserResponse = Depends(get_current_user)) -> list[CoinStrategyResponse]:
    """모든 코인 카테고리별 전략 설정."""
    db = get_db()
    rows = db.execute("SELECT * FROM coin_strategy_config ORDER BY category").fetchall()
    return [CoinStrategyResponse(**dict(r)) for r in rows]


@router.put("/{category}")
def update_coin_strategy(
    category: str,
    body: CoinStrategyUpdate,
    _: UserResponse = Depends(get_current_user),
) -> CoinStrategyResponse:
    """코인 카테고리 전략 설정 변경."""
    db = get_db()
    row = db.execute("SELECT * FROM coin_strategy_config WHERE category = ?", (category,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"카테고리 '{category}' 없음")

    db.execute(
        """UPDATE coin_strategy_config
        SET strategy_name = ?, stop_loss_pct = ?, trailing_stop_pct = ?,
            position_size_pct = ?, strategy_params_json = ?, updated_at = ?
        WHERE category = ?""",
        (body.strategy_name, body.stop_loss_pct, body.trailing_stop_pct,
         body.position_size_pct, body.strategy_params_json,
         datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), category),
    )
    db.commit()

    updated = db.execute("SELECT * FROM coin_strategy_config WHERE category = ?", (category,)).fetchone()
    return CoinStrategyResponse(**dict(updated))
