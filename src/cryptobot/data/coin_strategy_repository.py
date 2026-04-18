"""코인별 전략 배정 (#152).

LLM이 coin_strategies dict로 지정한 코인별 전략을 DB에 upsert.
StrategySelector가 매매 판단 시 이 테이블에서 코인별 전략을 조회.

진동 방지:
- min_hold_minutes 동안 같은 코인 재전환 금지
- 보유 포지션 있는 동안 전략 변경 금지 (호출자가 체크)
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from cryptobot.data.database import Database

logger = logging.getLogger(__name__)


def _clip_to_hard_limits(params: dict) -> tuple[dict, list[dict]]:
    """#188: coin_strategy_assignment 저장 직전 HARD_LIMITS 범위로 클리핑.

    LLM이 범위 밖 값(예: bb_std=5.0, rsi_oversold=100)을 보내도 실제 전략에는
    안전한 값만 적용되도록 한다. 원본과 클리핑 후 값을 함께 반환해 로깅.

    Returns:
        (clipped_params, clipped_log) — log는 [{field, original, clipped, range}]
    """
    # 순환 import 방지 — 함수 내부 import
    from cryptobot.llm.analyzer import HARD_LIMITS

    clipped = dict(params)
    log: list[dict] = []
    for key, val in list(params.items()):
        if key not in HARD_LIMITS:
            continue
        try:
            fv = float(val)
        except (ValueError, TypeError):
            continue
        mn, mx = HARD_LIMITS[key]
        new_val = max(mn, min(mx, fv))
        if new_val != fv:
            clipped[key] = new_val
            log.append({"field": key, "original": fv, "clipped": new_val, "range": [mn, mx]})
    return clipped, log


class CoinStrategyRepository:
    """coin_strategy_assignment 테이블 CRUD."""

    def __init__(self, db: Database, min_hold_minutes: int = 60) -> None:
        self._db = db
        self._min_hold_minutes = min_hold_minutes

    def get_assignment(self, coin: str) -> dict | None:
        """코인의 현재 배정 전략. 없으면 None."""
        row = self._db.execute(
            "SELECT * FROM coin_strategy_assignment WHERE coin = ?",
            (coin,),
        ).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("params_json"):
            try:
                d["params"] = json.loads(d["params_json"])
            except json.JSONDecodeError:
                d["params"] = {}
        return d

    def get_all_assignments(self) -> dict[str, dict]:
        """전체 배정 상태. {coin: assignment_dict}."""
        rows = self._db.execute("SELECT * FROM coin_strategy_assignment").fetchall()
        result = {}
        for row in rows:
            d = dict(row)
            if d.get("params_json"):
                try:
                    d["params"] = json.loads(d["params_json"])
                except json.JSONDecodeError:
                    d["params"] = {}
            result[d["coin"]] = d
        return result

    def assign(
        self,
        coin: str,
        strategy_name: str,
        params: dict | None = None,
        assigned_by: str = "llm",
        reason: str | None = None,
        *,
        force: bool = False,
    ) -> bool:
        """코인에 전략 배정.

        기본 가드:
        - min_hold_minutes 내에 이미 배정된 경우 재배정 거부 (force=True로 우회)
        - 같은 전략으로 재배정 시에도 allowed (파라미터 업데이트용)

        Returns:
            True: 배정 성공, False: 진동 방지 가드로 거부
        """
        existing = self.get_assignment(coin)

        if existing and not force:
            # 같은 전략이면 파라미터만 갱신 (진동 아님)
            if existing["strategy_name"] == strategy_name:
                pass  # 파라미터만 업데이트
            else:
                # 다른 전략으로 전환 — 최근 배정 후 N분 경과했는지 체크
                try:
                    prev_at = datetime.fromisoformat(existing["assigned_at"])
                    if prev_at.tzinfo is None:
                        prev_at = prev_at.replace(tzinfo=timezone.utc)
                    elapsed_min = (datetime.now(timezone.utc) - prev_at).total_seconds() / 60
                    if elapsed_min < self._min_hold_minutes:
                        logger.warning(
                            "전략 진동 방지: %s (%.0f분 전 %s → %s 요청 거부)",
                            coin,
                            elapsed_min,
                            existing["strategy_name"],
                            strategy_name,
                        )
                        return False
                except (ValueError, TypeError):
                    pass  # 타임스탬프 파싱 실패 시 허용

        # #188: HARD_LIMITS 범위 밖 파라미터 클리핑 (저장 전)
        # LLM이 bb_std=5.0, rsi_oversold=100 같은 범위 밖 값 보내도 안전한 값만 저장됨
        clipped_log: list[dict] = []
        if params is not None:
            params, clipped_log = _clip_to_hard_limits(params)
            if clipped_log:
                logger.warning(
                    "coin_strategy_assignment 파라미터 클리핑: coin=%s | %s",
                    coin,
                    ", ".join(f"{c['field']}: {c['original']}→{c['clipped']}" for c in clipped_log),
                )

        # #186: None과 빈 dict 구분 — 빈 dict는 명시적 "기본값 사용" 의사 표현
        params_json = json.dumps(params, ensure_ascii=False) if params is not None else None
        self._db.execute(
            """
            INSERT INTO coin_strategy_assignment (coin, strategy_name, params_json, assigned_by, reason, assigned_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(coin) DO UPDATE SET
                strategy_name = excluded.strategy_name,
                params_json = excluded.params_json,
                assigned_by = excluded.assigned_by,
                reason = excluded.reason,
                assigned_at = excluded.assigned_at
            """,
            (
                coin,
                strategy_name,
                params_json,
                assigned_by,
                reason,
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            ),
        )
        self._db.commit()
        return True

    def remove(self, coin: str) -> None:
        """배정 제거 (default_strategy로 폴백하게 됨)."""
        self._db.execute("DELETE FROM coin_strategy_assignment WHERE coin = ?", (coin,))
        self._db.commit()

    def apply_bulk(
        self,
        coin_strategies: dict[str, dict],
        available_strategies: set[str],
        held_coins: set[str] | None = None,
        active_coins: set[str] | None = None,
    ) -> dict:
        """LLM이 준 coin_strategies dict 일괄 적용.

        Args:
            coin_strategies: {coin: {"strategy": name, "params": {...}}}
            available_strategies: DB에 등록된 유효 전략명 집합
            held_coins: 보유 중인 코인 (전략 변경 금지 대상)
            active_coins: 현재 모니터링 중인 코인 (#186). 지정 시 외부 코인 배정 거부.
                None이면 기존 동작(필터 없음) 유지.

        Returns:
            {"applied": [...], "rejected": [{coin, strategy, reason}, ...]}
        """
        held_coins = held_coins or set()
        applied = []
        rejected = []

        for coin, spec in coin_strategies.items():
            coin_norm = coin if coin.startswith("KRW-") else f"KRW-{coin}"
            if not isinstance(spec, dict):
                rejected.append({"coin": coin_norm, "reason": "spec is not dict"})
                continue
            strategy = spec.get("strategy")
            if not strategy:
                rejected.append({"coin": coin_norm, "reason": "strategy missing"})
                continue
            if strategy not in available_strategies:
                rejected.append({"coin": coin_norm, "strategy": strategy, "reason": "unknown strategy"})
                continue
            # #186: 모니터링 외 코인 배정 거부 — 사용되지 않는 배정이 DB에 쌓이는 것 방지
            if active_coins is not None and coin_norm not in active_coins:
                rejected.append({"coin": coin_norm, "strategy": strategy, "reason": "coin not monitored"})
                continue
            if coin_norm in held_coins:
                # 보유 중인 코인은 전략 교체 금지 — 다음 라운드 때 반영
                existing = self.get_assignment(coin_norm)
                if existing and existing["strategy_name"] != strategy:
                    rejected.append(
                        {
                            "coin": coin_norm,
                            "strategy": strategy,
                            "reason": "held position — deferred",
                        }
                    )
                    continue

            params = spec.get("params") or {}
            ok = self.assign(
                coin_norm,
                strategy,
                params=params,
                assigned_by="llm",
                reason="coin_strategies bulk apply",
            )
            if ok:
                applied.append(coin_norm)
            else:
                rejected.append({"coin": coin_norm, "strategy": strategy, "reason": "min_hold_minutes"})

        return {"applied": applied, "rejected": rejected}
