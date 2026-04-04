"""봇 설정 관리 라우트."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/config", tags=["config"])


class ConfigItem(BaseModel):
    key: str
    value: str
    value_type: str
    category: str
    display_name: str
    description: str | None
    updated_at: str


class ConfigUpdate(BaseModel):
    value: str


@router.get("")
def get_all_config(_: UserResponse = Depends(get_current_user)) -> list[ConfigItem]:
    """모든 설정 조회."""
    db = get_db()
    rows = db.execute("SELECT * FROM bot_config ORDER BY category, key").fetchall()
    return [ConfigItem(**dict(r)) for r in rows]


@router.get("/{key}")
def get_config(key: str, _: UserResponse = Depends(get_current_user)) -> ConfigItem:
    """특정 설정 조회."""
    db = get_db()
    row = db.execute("SELECT * FROM bot_config WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"설정 '{key}' 없음")
    return ConfigItem(**dict(row))


@router.put("/{key}")
def update_config(
    key: str,
    body: ConfigUpdate,
    _: UserResponse = Depends(get_current_user),
) -> ConfigItem:
    """설정 값 변경."""
    db = get_db()
    row = db.execute("SELECT * FROM bot_config WHERE key = ?", (key,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"설정 '{key}' 없음")

    db.execute(
        "UPDATE bot_config SET value = ?, updated_at = ? WHERE key = ?",
        (body.value, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), key),
    )
    db.commit()

    updated = db.execute("SELECT * FROM bot_config WHERE key = ?", (key,)).fetchone()
    return ConfigItem(**dict(updated))
