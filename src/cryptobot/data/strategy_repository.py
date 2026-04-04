"""전략 DB 관리 모듈.

전략 마스터 정보 조회, 활성화/비활성화, 전환 이력 기록.
Admin API에서 사용.
"""

import json
import logging
from datetime import datetime, timezone

from cryptobot.data.database import Database

logger = logging.getLogger(__name__)


class StrategyRepository:
    """전략 DB 저장소."""

    def __init__(self, db: Database) -> None:
        self._db = db

    # ── 전략 마스터 조회 ──

    def get_all(self) -> list[dict]:
        """모든 전략 목록 조회."""
        rows = self._db.execute("SELECT * FROM strategies ORDER BY category, name").fetchall()
        return [dict(r) for r in rows]

    def get_by_name(self, name: str) -> dict | None:
        """전략 이름으로 조회."""
        row = self._db.execute("SELECT * FROM strategies WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def get_active(self) -> list[dict]:
        """현재 활성화된 전략 목록."""
        rows = self._db.execute("SELECT * FROM strategies WHERE is_active = TRUE ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def get_active_for_market(self, market_state: str) -> list[dict]:
        """특정 시장 상태에 활성화된 전략 목록."""
        rows = self._db.execute(
            "SELECT * FROM strategies WHERE is_active = TRUE AND market_states LIKE ?",
            (f"%{market_state}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_by_category(self, category: str) -> list[dict]:
        """카테고리별 전략 조회."""
        rows = self._db.execute(
            "SELECT * FROM strategies WHERE category = ? ORDER BY name",
            (category,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 전략 활성화/비활성화 ──

    def activate(self, name: str, source: str = "manual", reason: str | None = None) -> bool:
        """전략 활성화 (단일 활성화 — 기존 전략은 자동 종료).

        Args:
            name: 전략 이름
            source: 누가 활성화했는지 ("manual" / "llm" / "auto")
            reason: 활성화 사유

        Returns:
            성공 여부
        """
        strategy = self.get_by_name(name)
        if strategy is None:
            logger.warning("전략 '%s' 없음 — 활성화 실패", name)
            return False

        if strategy["is_active"] and strategy.get("status") == "active":
            return True  # 이미 활성화됨

        # 전환 중인 전략이 있으면 차단
        switching = self._db.execute(
            "SELECT name FROM strategies WHERE status = 'shutting_down'"
        ).fetchone()
        if switching:
            logger.warning("전략 '%s' 종료 중 — 전환 대기 필요", switching["name"])
            return False

        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 기존 활성 전략을 shutting_down으로 전환
        current_active = self._db.execute(
            "SELECT name FROM strategies WHERE is_active = TRUE AND name != ?",
            (name,),
        ).fetchall()

        for row in current_active:
            old_name = row["name"]
            self._db.execute(
                "UPDATE strategies SET status = 'shutting_down', updated_at = ? WHERE name = ?",
                (now, old_name),
            )
            self._record_activation(old_name, "shutting_down", source, f"전환: {old_name} → {name}")
            logger.info("전략 종료 중: %s → shutting_down", old_name)

        # 새 전략 활성화
        self._db.execute(
            "UPDATE strategies SET is_active = TRUE, status = 'active', updated_at = ? WHERE name = ?",
            (now, name),
        )
        self._record_activation(name, "activate", source, reason)
        self._db.commit()
        logger.info("전략 활성화: %s (by %s)", name, source)
        return True

    def complete_shutdown(self) -> list[str]:
        """shutting_down 상태의 전략을 inactive로 전환. 봇에서 주기적으로 호출.

        Returns:
            종료 완료된 전략 이름 목록
        """
        rows = self._db.execute(
            "SELECT name FROM strategies WHERE status = 'shutting_down'"
        ).fetchall()

        completed = []
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        for row in rows:
            name = row["name"]
            self._db.execute(
                "UPDATE strategies SET is_active = FALSE, status = 'inactive', updated_at = ? WHERE name = ?",
                (now, name),
            )
            self._record_activation(name, "deactivate", "auto", "전환 종료")
            completed.append(name)
            logger.info("전략 종료 완료: %s → inactive", name)

        if completed:
            self._db.commit()
        return completed

    def deactivate(self, name: str, source: str = "manual", reason: str | None = None) -> bool:
        """전략 비활성화."""
        strategy = self.get_by_name(name)
        if strategy is None:
            return False

        if not strategy["is_active"] and strategy.get("status") == "inactive":
            return True

        self._db.execute(
            "UPDATE strategies SET is_active = FALSE, status = 'inactive', updated_at = ? WHERE name = ?",
            (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), name),
        )
        self._record_activation(name, "deactivate", source, reason)
        self._db.commit()
        logger.info("전략 비활성화: %s (by %s)", name, source)
        return True

    def switch(
        self,
        from_strategy: str,
        to_strategy: str,
        source: str = "auto",
        market_state: str | None = None,
        reason: str | None = None,
        performance: dict | None = None,
    ) -> bool:
        """전략 전환 (이전 전략 비활성화 + 새 전략 활성화).

        Args:
            from_strategy: 이전 전략
            to_strategy: 새 전략
            source: 전환 주체 ("auto" / "llm" / "manual")
            market_state: 전환 시점 시장 상태
            reason: 전환 사유
            performance: 이전 전략의 성과 데이터
        """
        self.deactivate(from_strategy, source, f"전환: {from_strategy} → {to_strategy}")
        self.activate(to_strategy, source, reason)

        # 전환 이력에 추가 정보 기록
        self._db.execute(
            """
            UPDATE strategy_activations
            SET market_state = ?, previous_strategy = ?, performance_at_switch_json = ?
            WHERE id = (SELECT MAX(id) FROM strategy_activations WHERE strategy_name = ?)
            """,
            (
                market_state,
                from_strategy,
                json.dumps(performance) if performance else None,
                to_strategy,
            ),
        )
        self._db.commit()
        logger.info("전략 전환: %s → %s (시장: %s, 사유: %s)", from_strategy, to_strategy, market_state, reason)
        return True

    # ── 전략 파라미터 관리 ──

    def update_params(self, name: str, params_json: str) -> bool:
        """전략 기본 파라미터 업데이트."""
        self._db.execute(
            "UPDATE strategies SET default_params_json = ?, updated_at = ? WHERE name = ?",
            (params_json, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), name),
        )
        self._db.commit()
        return True

    # ── 활성화 이력 ──

    def get_activation_history(self, limit: int = 50) -> list[dict]:
        """전략 활성화/비활성화/전환 이력 조회."""
        rows = self._db.execute(
            "SELECT * FROM strategy_activations ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_strategy_stats(self, strategy_name: str) -> dict:
        """특정 전략의 매매 통계.

        Returns:
            총 거래 수, 승률, 평균 수익률, 총 수익금 등
        """
        row = self._db.execute(
            """
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN side='sell' AND profit_pct > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN side='sell' AND profit_pct <= 0 THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN side='sell' THEN profit_pct END) as avg_profit_pct,
                SUM(CASE WHEN side='sell' THEN profit_krw ELSE 0 END) as total_profit_krw,
                SUM(fee_krw) as total_fees
            FROM trades WHERE strategy = ?
            """,
            (strategy_name,),
        ).fetchone()

        if row is None or row["total_trades"] == 0:
            return {"total_trades": 0, "win_rate": 0, "avg_profit_pct": 0, "total_profit_krw": 0}

        sells = (row["wins"] or 0) + (row["losses"] or 0)
        win_rate = (row["wins"] or 0) / sells * 100 if sells > 0 else 0

        return {
            "total_trades": row["total_trades"],
            "wins": row["wins"] or 0,
            "losses": row["losses"] or 0,
            "win_rate": round(win_rate, 1),
            "avg_profit_pct": round(row["avg_profit_pct"] or 0, 2),
            "total_profit_krw": round(row["total_profit_krw"] or 0, 2),
            "total_fees": round(row["total_fees"] or 0, 2),
        }

    def _record_activation(self, name: str, action: str, source: str, reason: str | None) -> None:
        """활성화 이력 기록."""
        self._db.execute(
            """
            INSERT INTO strategy_activations (strategy_name, action, source, reason)
            VALUES (?, ?, ?, ?)
            """,
            (name, action, source, reason),
        )
