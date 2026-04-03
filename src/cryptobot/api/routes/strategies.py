"""전략 관리 라우트."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_strategy_repo

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ActivateRequest(BaseModel):
    reason: str | None = None


@router.get("")
def get_strategies(_: UserResponse = Depends(get_current_user)):
    """전략 목록 (메타 정보 + 활성화 상태)."""
    repo = get_strategy_repo()
    strategies = repo.get_all()

    # 전략별 통계도 함께 반환
    for s in strategies:
        s["stats"] = repo.get_strategy_stats(s["name"])

    return strategies


@router.get("/active")
def get_active_strategies(_: UserResponse = Depends(get_current_user)):
    """현재 활성화된 전략."""
    repo = get_strategy_repo()
    return repo.get_active()


@router.get("/activations")
def get_activation_history(limit: int = 50, _: UserResponse = Depends(get_current_user)):
    """전략 전환 이력."""
    repo = get_strategy_repo()
    return repo.get_activation_history(limit)


@router.get("/{name}")
def get_strategy_detail(name: str, _: UserResponse = Depends(get_current_user)):
    """전략 상세 (메타 + 통계)."""
    repo = get_strategy_repo()
    strategy = repo.get_by_name(name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"전략 '{name}'을 찾을 수 없습니다")

    strategy["stats"] = repo.get_strategy_stats(name)
    return strategy


@router.get("/{name}/stats")
def get_strategy_stats(name: str, _: UserResponse = Depends(get_current_user)):
    """전략별 매매 통계."""
    repo = get_strategy_repo()
    if repo.get_by_name(name) is None:
        raise HTTPException(status_code=404, detail=f"전략 '{name}'을 찾을 수 없습니다")
    return repo.get_strategy_stats(name)


@router.put("/{name}/activate")
def activate_strategy(name: str, body: ActivateRequest = None, _: UserResponse = Depends(get_current_user)):
    """전략 활성화."""
    repo = get_strategy_repo()
    reason = body.reason if body else None
    success = repo.activate(name, source="manual", reason=reason)
    if not success:
        raise HTTPException(status_code=404, detail=f"전략 '{name}'을 찾을 수 없습니다")
    return {"status": "activated", "strategy": name}


@router.put("/{name}/deactivate")
def deactivate_strategy(name: str, body: ActivateRequest = None, _: UserResponse = Depends(get_current_user)):
    """전략 비활성화."""
    repo = get_strategy_repo()
    reason = body.reason if body else None
    success = repo.deactivate(name, source="manual", reason=reason)
    if not success:
        raise HTTPException(status_code=404, detail=f"전략 '{name}'을 찾을 수 없습니다")
    return {"status": "deactivated", "strategy": name}
