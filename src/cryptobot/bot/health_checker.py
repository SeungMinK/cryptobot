"""일일 헬스체크 모듈.

매일 06:00에 실행하여 봇 상태를 점검한다:
1. 매매 정합성 (DB vs 업비트)
2. 뉴스 수집기 상태
3. 미체결 주문 정리
4. LLM 비용 일일 집계
5. DB 데이터 무결성
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class HealthChecker:
    """일일 헬스체크."""

    def __init__(self, db, trader=None, notifier=None) -> None:
        self._db = db
        self._trader = trader
        self._notifier = notifier

    def run_all(self) -> dict:
        """전체 헬스체크 실행. 결과를 dict로 반환."""
        results = {}

        results["trade_integrity"] = self._check_trade_integrity()
        results["news_collector"] = self._check_news_collector()
        results["pending_orders"] = self._check_pending_orders()
        results["llm_cost"] = self._check_llm_cost()
        results["data_integrity"] = self._check_data_integrity()

        # 전체 상태
        issues = [k for k, v in results.items() if v.get("status") == "warning"]
        results["overall"] = "healthy" if not issues else "warning"
        results["issues"] = issues
        results["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Slack 알림
        if self._notifier and issues:
            self._send_alert(results)
        elif self._notifier:
            self._notifier.send("✅ *일일 헬스체크 정상* — 이상 없음")

        logger.info("헬스체크 완료: %s (%d건 이상)", results["overall"], len(issues))
        return results

    def _check_trade_integrity(self) -> dict:
        """매매 정합성: 매수 후 매도 안 된 건 vs 실제 보유."""
        try:
            # DB에서 활성 매수 (매도 안 된 건)
            db_active = self._db.execute(
                """
                SELECT coin, price, amount, total_krw FROM trades t
                WHERE side = 'buy'
                AND NOT EXISTS (
                    SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell'
                )
                """
            ).fetchall()
            db_coins = {dict(r)["coin"] for r in db_active}

            # 실제 업비트 보유 확인
            if self._trader and self._trader.is_ready:
                upbit_coins = set()
                for coin in db_coins:
                    try:
                        bal = self._trader.get_balance_coin(coin)
                        if bal > 0:
                            upbit_coins.add(coin)
                    except Exception:
                        pass

                db_only = db_coins - upbit_coins  # DB에만 있음 (매도 누락?)
                upbit_only = upbit_coins - db_coins  # 업비트에만 있음 (매수 미기록?)

                if db_only or upbit_only:
                    logger.warning(
                        "매매 정합성 불일치: DB에만=%s, 업비트에만=%s",
                        db_only, upbit_only,
                    )
                    return {
                        "status": "warning",
                        "db_only": list(db_only),
                        "upbit_only": list(upbit_only),
                        "message": f"DB에만 {len(db_only)}건, 업비트에만 {len(upbit_only)}건",
                    }

                return {"status": "ok", "active_positions": len(db_coins)}
            return {"status": "ok", "message": "API 미설정 — 스킵"}
        except Exception as e:
            logger.error("매매 정합성 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def _check_news_collector(self) -> dict:
        """뉴스 수집기 상태: 24시간 내 수집 건수."""
        try:
            row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM news_articles WHERE collected_at >= datetime('now', '-24 hours')"
            ).fetchone()
            count = row[0] if row else 0

            fg_row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM fear_greed_index WHERE collected_at >= datetime('now', '-24 hours')"
            ).fetchone()
            fg_count = fg_row[0] if fg_row else 0

            if count == 0 and fg_count == 0:
                return {
                    "status": "warning",
                    "news_count": count,
                    "fg_count": fg_count,
                    "message": "24시간 내 뉴스+F&G 수집 0건 — 수집기 중단 의심",
                }

            return {
                "status": "ok",
                "news_count": count,
                "fg_count": fg_count,
            }
        except Exception as e:
            logger.error("뉴스 수집기 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def _check_pending_orders(self) -> dict:
        """미체결 주문 확인 및 정리."""
        try:
            if not self._trader or not self._trader.is_ready:
                return {"status": "ok", "message": "API 미설정 — 스킵"}


            # 활성 코인 목록
            coins = self._db.execute(
                """
                SELECT DISTINCT coin FROM trades
                WHERE side = 'buy'
                AND NOT EXISTS (
                    SELECT 1 FROM trades s WHERE s.buy_trade_id = trades.id AND s.side = 'sell'
                )
                """
            ).fetchall()

            total_cancelled = 0
            for r in coins:
                coin = dict(r)["coin"]
                cancelled = self._trader.cancel_all_orders(coin)
                total_cancelled += cancelled

            if total_cancelled > 0:
                logger.info("미체결 주문 %d건 취소", total_cancelled)
                return {
                    "status": "warning",
                    "cancelled": total_cancelled,
                    "message": f"미체결 주문 {total_cancelled}건 자동 취소",
                }

            return {"status": "ok", "cancelled": 0}
        except Exception as e:
            logger.error("미체결 주문 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def _check_llm_cost(self) -> dict:
        """LLM 비용 일일 집계."""
        try:
            row = self._db.execute(
                """
                SELECT COUNT(*) as calls, COALESCE(SUM(cost_usd), 0) as total_cost
                FROM llm_decisions
                WHERE DATE(timestamp) = DATE('now')
                """
            ).fetchone()

            calls = row[0] if row else 0
            cost = row[1] if row else 0

            status = "warning" if calls > 10 else "ok"
            return {
                "status": status,
                "calls": calls,
                "cost_usd": round(cost, 4),
                "message": f"LLM {calls}회 호출, ${cost:.4f}" if calls > 10 else None,
            }
        except Exception as e:
            logger.error("LLM 비용 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def _check_data_integrity(self) -> dict:
        """DB 데이터 무결성."""
        try:
            issues = []

            # 매도인데 buy_trade_id 없는 건
            row = self._db.execute(
                "SELECT COUNT(*) FROM trades WHERE side = 'sell' AND buy_trade_id IS NULL"
            ).fetchone()
            orphan_sells = row[0] if row else 0
            if orphan_sells > 0:
                issues.append(f"매도 {orphan_sells}건에 buy_trade_id 없음")

            # 실행된 신호인데 trade_id 없는 건
            row = self._db.execute(
                "SELECT COUNT(*) FROM trade_signals WHERE executed = 1 AND trade_id IS NULL"
            ).fetchone()
            orphan_signals = row[0] if row else 0
            if orphan_signals > 0:
                issues.append(f"실행된 신호 {orphan_signals}건에 trade_id 없음")

            # 가격 0인 스냅샷
            row = self._db.execute(
                """
                SELECT COUNT(*) FROM market_snapshots
                WHERE price IS NULL OR price = 0
                AND timestamp >= datetime('now', '-24 hours')
                """
            ).fetchone()
            bad_snapshots = row[0] if row else 0
            if bad_snapshots > 0:
                issues.append(f"가격 0/NULL 스냅샷 {bad_snapshots}건 (24시간)")

            if issues:
                return {
                    "status": "warning",
                    "issues": issues,
                    "message": "; ".join(issues),
                }

            return {"status": "ok"}
        except Exception as e:
            logger.error("데이터 무결성 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def _send_alert(self, results: dict) -> None:
        """이상 발견 시 Slack 알림."""
        lines = ["⚠️ *일일 헬스체크 이상 발견*\n"]
        for key in results.get("issues", []):
            detail = results.get(key, {})
            msg = detail.get("message", "상세 정보 없음")
            lines.append(f"• *{key}*: {msg}")

        self._notifier.send("\n".join(lines))
