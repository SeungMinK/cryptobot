"""전략 관리 라우트."""

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from cryptobot.api.auth import UserResponse, get_current_user
from cryptobot.api.deps import get_db, get_strategy_repo

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ActivateRequest(BaseModel):
    reason: str | None = None


class ParamsUpdateRequest(BaseModel):
    params_json: str


class SimulateRequest(BaseModel):
    params_json: str


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
    """전략 활성화 (기존 전략은 자동 종료)."""
    repo = get_strategy_repo()
    reason = body.reason if body else None
    success = repo.activate(name, source="manual", reason=reason)
    if not success:
        # 전환 중이거나 전략이 없는 경우
        switching = repo._db.execute("SELECT name FROM strategies WHERE status = 'shutting_down'").fetchone()
        if switching:
            raise HTTPException(status_code=409, detail=f"전략 '{switching['name']}' 종료 중 — 잠시 후 다시 시도")
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


@router.put("/{name}/params")
def update_strategy_params(name: str, body: ParamsUpdateRequest, _: UserResponse = Depends(get_current_user)):
    """전략 파라미터 업데이트."""
    repo = get_strategy_repo()
    strategy = repo.get_by_name(name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"전략 '{name}'을 찾을 수 없습니다")

    # JSON 유효성 검증
    try:
        json.loads(body.params_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="유효하지 않은 JSON")

    repo.update_params(name, body.params_json)
    return {"status": "updated", "strategy": name}


@router.post("/{name}/simulate")
def simulate_strategy(name: str, body: SimulateRequest, _: UserResponse = Depends(get_current_user)):
    """파라미터 변경 시 예상 동작을 시뮬레이션.

    현재 시장 데이터 기반으로 현재값 vs 변경값 비교.
    """
    repo = get_strategy_repo()
    strategy = repo.get_by_name(name)
    if strategy is None:
        raise HTTPException(status_code=404, detail=f"전략 '{name}'을 찾을 수 없습니다")

    try:
        new_params = json.loads(body.params_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="유효하지 않은 JSON")

    current_params = json.loads(strategy["default_params_json"]) if strategy["default_params_json"] else {}

    # 최신 market snapshot에서 시뮬레이션 데이터 가져오기
    db = get_db()
    snapshot = db.execute("SELECT * FROM market_snapshots ORDER BY id DESC LIMIT 1").fetchone()

    simulation = {}
    if snapshot:
        snapshot = dict(snapshot)
        ma_20 = snapshot.get("ma_20")
        bb_upper = snapshot.get("bb_upper")
        current_price = snapshot.get("price", 0)
        yesterday_high = snapshot.get("high_24h", 0)
        yesterday_low = snapshot.get("low_24h", 0)
        today_open = snapshot.get("open_24h", 0)
        price_range = yesterday_high - yesterday_low

        # 현재 std 계산 (bb_upper, ma_20에서 역산)
        if ma_20 and bb_upper and bb_upper != ma_20:
            current_bb_std = current_params.get("bb_std", 2.0)
            one_std = (bb_upper - ma_20) / current_bb_std if current_bb_std != 0 else 0

            if name in ("bollinger_bands", "bollinger_squeeze"):
                new_bb_std = new_params.get("bb_std", current_bb_std)
                simulation = {
                    "current_price": current_price,
                    "ma_20": ma_20,
                    "one_std": round(one_std),
                    "current_upper": round(ma_20 + one_std * current_bb_std),
                    "current_lower": round(ma_20 - one_std * current_bb_std),
                    "current_band_width": round(one_std * current_bb_std * 2),
                    "new_upper": round(ma_20 + one_std * new_bb_std),
                    "new_lower": round(ma_20 - one_std * new_bb_std),
                    "new_band_width": round(one_std * new_bb_std * 2),
                    "current_distance_to_lower": round(current_price - (ma_20 - one_std * current_bb_std)),
                    "new_distance_to_lower": round(current_price - (ma_20 - one_std * new_bb_std)),
                    "current_distance_to_lower_pct": round(
                        (current_price - (ma_20 - one_std * current_bb_std)) / current_price * 100, 2
                    ),
                    "new_distance_to_lower_pct": round(
                        (current_price - (ma_20 - one_std * new_bb_std)) / current_price * 100, 2
                    ),
                }

        if name == "volatility_breakout":
            current_k = current_params.get("k_value", 0.5)
            new_k = new_params.get("k_value", current_k)
            simulation = {
                "current_price": current_price,
                "today_open": today_open,
                "price_range": round(price_range),
                "current_breakout": round(today_open + price_range * current_k),
                "new_breakout": round(today_open + price_range * new_k),
                "current_distance": round(current_price - (today_open + price_range * current_k)),
                "new_distance": round(current_price - (today_open + price_range * new_k)),
            }

        if name == "ma_crossover":
            simulation = {
                "current_price": current_price,
                "ma_5": snapshot.get("ma_5"),
                "ma_20": ma_20,
                "current_short_period": current_params.get("short_period", 5),
                "current_long_period": current_params.get("long_period", 20),
                "new_short_period": new_params.get("short_period", current_params.get("short_period", 5)),
                "new_long_period": new_params.get("long_period", current_params.get("long_period", 20)),
            }

        if name == "rsi_mean_reversion":
            rsi = snapshot.get("rsi_14", 0)
            simulation = {
                "current_rsi": rsi,
                "current_oversold": current_params.get("oversold", 30),
                "current_overbought": current_params.get("overbought", 70),
                "new_oversold": new_params.get("oversold", current_params.get("oversold", 30)),
                "new_overbought": new_params.get("overbought", current_params.get("overbought", 70)),
                "current_buy_distance": round(rsi - current_params.get("oversold", 30), 1),
                "new_buy_distance": round(rsi - new_params.get("oversold", current_params.get("oversold", 30)), 1),
            }

        if name == "breakout_momentum":
            simulation = {
                "current_price": current_price,
                "current_entry_period": current_params.get("entry_period", 20),
                "current_exit_period": current_params.get("exit_period", 10),
                "new_entry_period": new_params.get("entry_period", current_params.get("entry_period", 20)),
                "new_exit_period": new_params.get("exit_period", current_params.get("exit_period", 10)),
            }

    return {
        "strategy": name,
        "current_params": current_params,
        "new_params": new_params,
        "simulation": simulation,
    }
