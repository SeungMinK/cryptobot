"""월간 감사 모듈.

매월 1일 04:00에 실행:
1. 월간 수익률 서머리
2. LLM 비용 월간 정산
3. DB 백업
4. 로그 파일 관리
"""

import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


class MonthlyAudit:
    """월간 감사."""

    BACKUP_DIR = Path(__file__).resolve().parent.parent.parent.parent / "backups"
    BACKUP_KEEP_MONTHS = 3

    def __init__(self, db, db_path: Path | str, notifier=None) -> None:
        self._db = db
        self._db_path = Path(db_path)
        self._notifier = notifier

    def run_all(self) -> dict:
        """전체 월간 감사 실행."""
        results = {}

        results["monthly_summary"] = self._monthly_summary()
        results["llm_cost"] = self._llm_monthly_cost()
        results["db_backup"] = self._db_backup()
        results["log_cleanup"] = self._log_cleanup()
        results["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if self._notifier:
            self._send_report(results)

        logger.info("월간 감사 완료")
        return results

    def _monthly_summary(self) -> dict:
        """월간 수익률 서머리."""
        try:
            row = self._db.execute(
                """
                SELECT
                    COUNT(*) as total_sells,
                    SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                    COALESCE(SUM(profit_krw), 0) as total_pnl,
                    COALESCE(SUM(fee_krw), 0) as total_fees,
                    COALESCE(MAX(profit_krw), 0) as best_trade,
                    COALESCE(MIN(profit_krw), 0) as worst_trade,
                    COALESCE(AVG(profit_pct), 0) as avg_pct
                FROM trades
                WHERE side = 'sell'
                AND timestamp >= datetime('now', 'start of month', '-1 month')
                AND timestamp < datetime('now', 'start of month')
                """
            ).fetchone()
            r = dict(row) if row else {}

            total = r.get("total_sells", 0) or 0
            wins = r.get("wins", 0) or 0
            win_rate = round(wins / total * 100, 1) if total > 0 else 0

            # 전략별 기여도
            strategy_rows = self._db.execute(
                """
                SELECT strategy, COUNT(*) as cnt,
                    COALESCE(SUM(profit_krw), 0) as pnl
                FROM trades
                WHERE side = 'sell'
                AND timestamp >= datetime('now', 'start of month', '-1 month')
                AND timestamp < datetime('now', 'start of month')
                GROUP BY strategy ORDER BY pnl DESC
                """
            ).fetchall()
            strategies = [
                {"strategy": dict(s)["strategy"], "trades": dict(s)["cnt"], "pnl": dict(s)["pnl"]}
                for s in strategy_rows
            ]

            # 총 매수 건수
            buy_row = self._db.execute(
                """
                SELECT COUNT(*) as cnt, COALESCE(SUM(fee_krw), 0) as fees
                FROM trades
                WHERE side = 'buy'
                AND timestamp >= datetime('now', 'start of month', '-1 month')
                AND timestamp < datetime('now', 'start of month')
                """
            ).fetchone()
            buy_count = dict(buy_row)["cnt"] if buy_row else 0
            total_fees = (r.get("total_fees", 0) or 0) + (dict(buy_row)["fees"] if buy_row else 0)

            return {
                "status": "ok",
                "total_trades": total + buy_count,
                "sells": total,
                "wins": wins,
                "win_rate": win_rate,
                "total_pnl": round(r.get("total_pnl", 0) or 0, 0),
                "total_fees": round(total_fees, 0),
                "best_trade": round(r.get("best_trade", 0) or 0, 0),
                "worst_trade": round(r.get("worst_trade", 0) or 0, 0),
                "avg_pct": round(r.get("avg_pct", 0) or 0, 2),
                "strategies": strategies,
            }
        except Exception as e:
            logger.error("월간 서머리 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _llm_monthly_cost(self) -> dict:
        """LLM 비용 월간 정산."""
        try:
            row = self._db.execute(
                """
                SELECT COUNT(*) as calls,
                    COALESCE(SUM(cost_usd), 0) as total_cost,
                    COALESCE(SUM(input_tokens), 0) as total_input,
                    COALESCE(SUM(output_tokens), 0) as total_output
                FROM llm_decisions
                WHERE timestamp >= datetime('now', 'start of month', '-1 month')
                AND timestamp < datetime('now', 'start of month')
                """
            ).fetchone()
            r = dict(row) if row else {}

            cost_usd = round(r.get("total_cost", 0) or 0, 4)
            cost_krw = round(cost_usd * 1400, 0)  # 대략적 환율

            return {
                "status": "ok",
                "calls": r.get("calls", 0) or 0,
                "cost_usd": cost_usd,
                "cost_krw": cost_krw,
                "total_input_tokens": r.get("total_input", 0) or 0,
                "total_output_tokens": r.get("total_output", 0) or 0,
            }
        except Exception as e:
            logger.error("LLM 비용 정산 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _db_backup(self) -> dict:
        """DB 백업 (SQLite 파일 복사)."""
        try:
            self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

            backup_name = f"cryptobot_{date.today().isoformat()}.db"
            backup_path = self.BACKUP_DIR / backup_name

            shutil.copy2(str(self._db_path), str(backup_path))
            size_mb = round(backup_path.stat().st_size / 1024 / 1024, 2)

            logger.info("DB 백업 완료: %s (%.2fMB)", backup_path, size_mb)

            # 오래된 백업 정리 (BACKUP_KEEP_MONTHS개월)
            deleted = self._cleanup_old_backups()

            return {
                "status": "ok",
                "path": str(backup_path),
                "size_mb": size_mb,
                "old_deleted": deleted,
            }
        except Exception as e:
            logger.error("DB 백업 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _cleanup_old_backups(self) -> int:
        """오래된 백업 파일 정리."""
        if not self.BACKUP_DIR.exists():
            return 0

        backups = sorted(self.BACKUP_DIR.glob("cryptobot_*.db"))
        deleted = 0
        while len(backups) > self.BACKUP_KEEP_MONTHS:
            old = backups.pop(0)
            old.unlink()
            deleted += 1
            logger.info("오래된 백업 삭제: %s", old.name)
        return deleted

    def _log_cleanup(self) -> dict:
        """30일 이상 된 로그 디렉토리 정리."""
        try:
            log_dir = Path(__file__).resolve().parent.parent.parent.parent / "error"
            if not log_dir.exists():
                return {"status": "ok", "deleted": 0}

            deleted = 0
            today = date.today()
            for day_dir in sorted(log_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                try:
                    dir_date = date.fromisoformat(day_dir.name)
                    if (today - dir_date).days > 30:
                        shutil.rmtree(day_dir)
                        deleted += 1
                        logger.info("로그 디렉토리 삭제: %s", day_dir.name)
                except ValueError:
                    continue

            return {"status": "ok", "deleted": deleted}
        except Exception as e:
            logger.error("로그 정리 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _send_report(self, results: dict) -> None:
        """Slack 월간 리포트."""
        lines = ["📋 *월간 감사 리포트*\n"]

        # 수익률 서머리
        s = results.get("monthly_summary", {})
        if s.get("status") == "ok":
            emoji = "📈" if (s.get("total_pnl", 0) or 0) >= 0 else "📉"
            lines.append(f"{emoji} *전월 실적*")
            lines.append(
                f"  총 {s.get('total_trades', 0)}건 거래, 매도 {s.get('sells', 0)}건, 승률 {s.get('win_rate', 0)}%"
            )
            lines.append(f"  총 손익: {s.get('total_pnl', 0):+,.0f}원")
            lines.append(f"  총 수수료: {s.get('total_fees', 0):,.0f}원")
            lines.append(f"  최고: {s.get('best_trade', 0):+,.0f}원 / 최악: {s.get('worst_trade', 0):+,.0f}원")

            strategies = s.get("strategies", [])
            if strategies:
                lines.append("  전략별:")
                for st in strategies:
                    lines.append(f"    {st['strategy']}: {st['trades']}건, {st['pnl']:+,.0f}원")

        # LLM 비용
        llm = results.get("llm_cost", {})
        if llm.get("status") == "ok":
            lines.append(
                f"\n💰 *LLM 비용*: ${llm.get('cost_usd', 0):.4f} "
                f"(≈{llm.get('cost_krw', 0):,.0f}원, "
                f"{llm.get('calls', 0)}회)"
            )

        # DB 백업
        db = results.get("db_backup", {})
        if db.get("status") == "ok":
            lines.append(f"💾 *DB 백업*: {db.get('size_mb', '?')}MB")

        # 로그
        log = results.get("log_cleanup", {})
        log_del = log.get("deleted", 0)
        if log_del > 0:
            lines.append(f"🗑️ *로그 정리*: {log_del}개 디렉토리 삭제")

        self._notifier.send("\n".join(lines))
