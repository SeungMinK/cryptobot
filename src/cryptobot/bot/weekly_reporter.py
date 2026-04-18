"""주간 리포트 모듈.

매주 일요일 03:00에 실행:
1. 전략 성과 비교 리포트
2. LLM 파라미터 드리프트 분석
3. DB 최적화 (ANALYZE)
4. 오래된 데이터 정리 (90일+)
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WeeklyReporter:
    """주간 리포트."""

    def __init__(self, db, notifier=None) -> None:
        self._db = db
        self._notifier = notifier

    def run_all(self) -> dict:
        """전체 주간 리포트 실행."""
        results = {}

        results["strategy_performance"] = self._strategy_performance()
        results["param_drift"] = self._param_drift()
        results["db_optimize"] = self._db_optimize()
        results["data_cleanup"] = self._data_cleanup()
        results["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        if self._notifier:
            self._send_report(results)

        logger.info("주간 리포트 완료")
        return results

    def _strategy_performance(self) -> dict:
        """전략별 주간 성과 비교."""
        try:
            rows = self._db.execute(
                """
                SELECT strategy,
                    COUNT(*) as trades,
                    SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                    ROUND(AVG(profit_pct), 2) as avg_pct,
                    ROUND(SUM(profit_krw), 0) as total_pnl
                FROM trades
                WHERE side = 'sell' AND timestamp >= datetime('now', '-7 days')
                GROUP BY strategy ORDER BY total_pnl DESC
                """
            ).fetchall()

            strategies = []
            for r in rows:
                r = dict(r)
                win_rate = round((r["wins"] or 0) / r["trades"] * 100, 1) if r["trades"] > 0 else 0
                strategies.append(
                    {
                        "strategy": r["strategy"],
                        "trades": r["trades"],
                        "win_rate": win_rate,
                        "avg_pct": r["avg_pct"] or 0,
                        "total_pnl": r["total_pnl"] or 0,
                    }
                )

            return {"status": "ok", "strategies": strategies}
        except Exception as e:
            logger.error("전략 성과 분석 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _param_drift(self) -> dict:
        """LLM 파라미터 드리프트 분석 (7일)."""
        try:
            rows = self._db.execute(
                """
                SELECT input_news_summary, datetime(timestamp, '+9 hours') as kst
                FROM llm_decisions
                WHERE timestamp >= datetime('now', '-7 days')
                ORDER BY id ASC
                """
            ).fetchall()

            changes = []
            for r in rows:
                r = dict(r)
                if r["input_news_summary"]:
                    try:
                        import json

                        ba = json.loads(r["input_news_summary"])
                        before = ba.get("before", {})
                        after = ba.get("after", {})
                        diff = {
                            k: {"before": before.get(k, "?"), "after": v}
                            for k, v in after.items()
                            if str(before.get(k, "?")) != str(v)
                        }
                        if diff:
                            changes.append(
                                {
                                    "timestamp": r["kst"],
                                    "changes": diff,
                                }
                            )
                    except Exception:
                        pass

            return {
                "status": "ok",
                "total_changes": len(changes),
                "details": changes[-5:],  # 최근 5건만
            }
        except Exception as e:
            logger.error("파라미터 드리프트 분석 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _db_optimize(self) -> dict:
        """DB 최적화 (ANALYZE + 크기 확인)."""
        try:
            # ANALYZE: 인덱스 통계 갱신
            self._db.execute("ANALYZE")
            self._db.commit()

            # DB 파일 크기
            row = self._db.execute(
                "SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()"
            ).fetchone()
            db_size_mb = round(row[0] / 1024 / 1024, 2) if row else 0

            # 테이블별 행 수
            tables = {}
            for table in [
                "trades",
                "trade_signals",
                "market_snapshots",
                "news_articles",
                "llm_decisions",
                "daily_reports",
            ]:
                r = self._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
                tables[table] = r[0] if r else 0

            logger.info("DB 최적화 완료: %.2fMB", db_size_mb)
            return {
                "status": "ok",
                "size_mb": db_size_mb,
                "tables": tables,
            }
        except Exception as e:
            logger.error("DB 최적화 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _data_cleanup(self) -> dict:
        """90일 이상 된 데이터 정리."""
        try:
            # market_snapshots 정리 (90일+)
            cursor = self._db.execute("DELETE FROM market_snapshots WHERE timestamp < datetime('now', '-90 days')")
            snapshots_deleted = cursor.rowcount

            # 미실행 신호 정리 (90일+)
            cursor = self._db.execute(
                """
                DELETE FROM trade_signals
                WHERE timestamp < datetime('now', '-90 days') AND executed = 0
                """
            )
            signals_deleted = cursor.rowcount

            self._db.commit()

            if snapshots_deleted > 0 or signals_deleted > 0:
                logger.info(
                    "데이터 정리: 스냅샷 %d건, 미실행 신호 %d건 삭제",
                    snapshots_deleted,
                    signals_deleted,
                )

            return {
                "status": "ok",
                "snapshots_deleted": snapshots_deleted,
                "signals_deleted": signals_deleted,
            }
        except Exception as e:
            logger.error("데이터 정리 실패: %s", e)
            return {"status": "error", "message": str(e)}

    def _send_report(self, results: dict) -> None:
        """Slack 주간 리포트."""
        lines = ["📊 *주간 리포트*\n"]

        # 전략 성과
        perf = results.get("strategy_performance", {})
        strategies = perf.get("strategies", [])
        if strategies:
            lines.append("*전략별 성과 (7일)*")
            for s in strategies:
                emoji = "🟢" if s["total_pnl"] > 0 else "🔴"
                lines.append(
                    f"  {emoji} {s['strategy']}: "
                    f"{s['trades']}건, 승률 {s['win_rate']}%, "
                    f"평균 {s['avg_pct']:+.2f}%, "
                    f"손익 {s['total_pnl']:+,.0f}원"
                )
        else:
            lines.append("*전략별 성과*: 7일간 매매 없음")

        # 파라미터 드리프트
        drift = results.get("param_drift", {})
        lines.append(f"\n*파라미터 변경*: {drift.get('total_changes', 0)}건")

        # DB
        db = results.get("db_optimize", {})
        lines.append(f"*DB 크기*: {db.get('size_mb', '?')}MB")

        cleanup = results.get("data_cleanup", {})
        snap_del = cleanup.get("snapshots_deleted", 0)
        sig_del = cleanup.get("signals_deleted", 0)
        if snap_del or sig_del:
            lines.append(f"*정리*: 스냅샷 {snap_del}건 + 신호 {sig_del}건 삭제")

        self._notifier.send("\n".join(lines))
