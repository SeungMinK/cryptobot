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
        results["trade_reconciliation"] = self.reconcile_trades()
        results["balance_check"] = self._check_balance_consistency()
        results["news_collector"] = self._check_news_collector()
        results["pending_orders"] = self._check_pending_orders()
        results["llm_cost"] = self._check_llm_cost()
        results["data_integrity"] = self._check_data_integrity()
        results["strategy_consistency"] = self._check_strategy_consistency()

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
                        db_only,
                        upbit_only,
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

    def _check_strategy_consistency(self) -> dict:
        """LLM 추천 vs DB 저장 vs 실제 신호 적용 — 3중 검증."""
        try:
            import json

            issues = []

            # 1. 활성 전략 확인
            active_row = self._db.execute(
                "SELECT name FROM strategies WHERE is_active = TRUE AND status = 'active' LIMIT 1"
            ).fetchone()
            active_name = dict(active_row)["name"] if active_row else "없음"

            # 2. DB 파라미터 범위 검증
            if active_row:
                strategy_row = self._db.execute(
                    "SELECT default_params_json FROM strategies WHERE name = ?",
                    (active_name,),
                ).fetchone()
                if strategy_row:
                    try:
                        db_params = json.loads(dict(strategy_row)["default_params_json"] or "{}")
                        rsi = db_params.get("rsi_oversold")
                        if rsi is not None and (rsi < 20 or rsi > 45):
                            issues.append(f"rsi_oversold={rsi} 범위 이탈 (20~45)")
                        bb = db_params.get("bb_std")
                        if bb is not None and (bb < 0.8 or bb > 2.5):
                            issues.append(f"bb_std={bb} 범위 이탈 (0.8~2.5)")
                    except json.JSONDecodeError:
                        issues.append("전략 파라미터 JSON 파싱 실패")

            # 3. LLM 설정값 vs 실제 신호에 적용된 값 비교
            llm_row = self._db.execute(
                "SELECT input_news_summary FROM llm_decisions ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if llm_row and dict(llm_row)["input_news_summary"]:
                try:
                    ba = json.loads(dict(llm_row)["input_news_summary"])
                    llm_strategy = ba.get("strategy")

                    # 전략 불일치
                    if llm_strategy and llm_strategy != active_name:
                        issues.append(f"전략 불일치: LLM 추천={llm_strategy}, 활성={active_name}")

                    # 최근 신호에 적용된 파라미터 확인
                    recent_signal = self._db.execute(
                        "SELECT strategy, strategy_params_json FROM trade_signals ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if recent_signal:
                        signal_strategy = dict(recent_signal)["strategy"]
                        signal_params_json = dict(recent_signal)["strategy_params_json"]

                        if signal_strategy != active_name:
                            issues.append(f"신호 전략 불일치: 신호={signal_strategy}, 활성={active_name}")

                        if signal_params_json and active_row:
                            try:
                                signal_params = json.loads(signal_params_json)
                                # rsi_oversold 비교
                                if "rsi_oversold" in db_params and "rsi_oversold" in signal_params:
                                    if db_params["rsi_oversold"] != signal_params["rsi_oversold"]:
                                        issues.append(
                                            f"rsi_oversold 미반영: DB={db_params['rsi_oversold']}, "
                                            f"신호={signal_params['rsi_oversold']}"
                                        )
                            except (json.JSONDecodeError, TypeError):
                                pass

                except (json.JSONDecodeError, TypeError):
                    pass

            if issues:
                return {"status": "warning", "active": active_name, "issues": issues, "message": "; ".join(issues)}
            return {"status": "ok", "active": active_name}
        except Exception as e:
            logger.error("전략 일관성 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def reconcile_trades(self) -> dict:
        """미검증 거래의 체결 정합성을 검증하고 보정한다.

        order_uuid가 있는 미검증(reconciled=0) 거래를 업비트 API로 확인하여
        실체결가와 DB 기록의 차이가 0.1% 이상이면 DB를 보정한다.

        Returns:
            검증 결과 dict
        """
        try:
            if not self._trader or not self._trader.is_ready:
                return {"status": "ok", "message": "API 미설정 — 스킵"}

            # 미검증 거래 조회 (최근 7일, order_uuid 있는 건)
            rows = self._db.execute(
                """
                SELECT id, coin, side, price, amount, total_krw, fee_krw, order_uuid, buy_trade_id
                FROM trades
                WHERE reconciled = 0
                  AND order_uuid IS NOT NULL
                  AND timestamp >= datetime('now', '-7 days')
                ORDER BY id
                """
            ).fetchall()

            if not rows:
                return {"status": "ok", "checked": 0, "corrected": 0}

            checked = 0
            corrected = 0
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

            for row in rows:
                trade = dict(row)
                detail = self._trader.get_order_detail(trade["order_uuid"])
                if not detail:
                    logger.warning("체결 상세 조회 실패 (trade_id=%d)", trade["id"])
                    continue

                checked += 1
                db_price = trade["price"]
                db_total = trade["total_krw"]
                actual_price = detail["price"]
                actual_total = detail["funds"]
                actual_fee = detail["fee"]
                actual_volume = detail["volume"]

                # 오차율 계산
                price_diff = abs(db_price - actual_price) / actual_price if actual_price > 0 else 0
                total_diff = abs(db_total - actual_total) / actual_total if actual_total > 0 else 0

                if price_diff > 0.001 or total_diff > 0.001:
                    # DB 보정
                    self._db.execute(
                        """
                        UPDATE trades
                        SET price = ?, amount = ?, total_krw = ?, fee_krw = ?,
                            reconciled = 2, reconciled_at = ?
                        WHERE id = ?
                        """,
                        (actual_price, actual_volume, actual_total, actual_fee, now_str, trade["id"]),
                    )
                    corrected += 1
                    logger.info(
                        "거래 보정: id=%d %s 가격 %.0f→%.0f 금액 %.0f→%.0f",
                        trade["id"],
                        trade["side"],
                        db_price,
                        actual_price,
                        db_total,
                        actual_total,
                    )

                    # 매도 거래의 profit 재계산
                    if trade["side"] == "sell" and trade["buy_trade_id"]:
                        self._recalculate_profit(trade["id"], trade["buy_trade_id"])
                else:
                    # 일치 확인
                    self._db.execute(
                        "UPDATE trades SET reconciled = 1, reconciled_at = ? WHERE id = ?",
                        (now_str, trade["id"]),
                    )

            self._db.commit()

            result = {"status": "ok", "checked": checked, "corrected": corrected}
            if corrected > 0:
                result["status"] = "warning"
                result["message"] = f"{corrected}건 보정됨 (총 {checked}건 검증)"
                logger.warning("체결 정합성: %d건 보정 / %d건 검증", corrected, checked)
            else:
                logger.info("체결 정합성: %d건 검증 완료 — 이상 없음", checked)

            return result
        except Exception as e:
            logger.error("체결 정합성 검증 실패: %s", e, exc_info=True)
            return {"status": "warning", "message": str(e)}

    def _recalculate_profit(self, sell_trade_id: int, buy_trade_id: int) -> None:
        """보정된 매수/매도 값 기준으로 profit_krw, profit_pct를 재계산한다."""
        try:
            buy = self._db.execute("SELECT total_krw, fee_krw FROM trades WHERE id = ?", (buy_trade_id,)).fetchone()
            sell = self._db.execute("SELECT total_krw, fee_krw FROM trades WHERE id = ?", (sell_trade_id,)).fetchone()

            if not buy or not sell:
                return

            buy = dict(buy)
            sell = dict(sell)
            buy_cost = buy["total_krw"] + (buy["fee_krw"] or 0)
            sell_revenue = sell["total_krw"] - (sell["fee_krw"] or 0)
            profit_krw = round(sell_revenue - buy_cost, 2)
            profit_pct = round(profit_krw / buy_cost * 100, 2) if buy_cost > 0 else 0

            self._db.execute(
                "UPDATE trades SET profit_krw = ?, profit_pct = ? WHERE id = ?",
                (profit_krw, profit_pct, sell_trade_id),
            )
            logger.info("수익 재계산: sell_id=%d profit=%.0f원 (%.2f%%)", sell_trade_id, profit_krw, profit_pct)
        except Exception as e:
            logger.error("수익 재계산 실패 (sell_id=%d): %s", sell_trade_id, e)

    def _check_balance_consistency(self) -> dict:
        """DB 역산 잔고 vs 실제 업비트 KRW 잔고 비교.

        차이 > 2%이면 미검증 거래를 즉시 재보정한 후 재확인.
        재보정 후에도 차이 > 2%이면 Slack 경고.
        """
        try:
            if not self._trader or not self._trader.is_ready:
                return {"status": "ok", "message": "API 미설정 — 스킵"}

            # 실제 업비트 자산 조회
            actual_krw = self._trader.get_balance_krw()

            import pyupbit

            active_rows = self._db.execute(
                """
                SELECT coin, amount FROM trades t
                WHERE side = 'buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
                """
            ).fetchall()
            coin_value = 0
            for ar in active_rows:
                ad = dict(ar)
                cp = pyupbit.get_current_price(ad["coin"])
                if cp:
                    coin_value += ad["amount"] * cp

            total_actual = actual_krw + coin_value
            logger.info("잔고 검증: KRW=%.0f 코인=%.0f 합계=%.0f", actual_krw, coin_value, total_actual)

            # DB 기준 총자산 역산
            db_total = self._calculate_db_total_asset()

            if total_actual <= 0 or db_total <= 0:
                return {"status": "ok", "krw_balance": actual_krw, "coin_value": coin_value, "total": total_actual}

            diff_pct = abs(total_actual - db_total) / total_actual * 100

            if diff_pct > 2.0:
                logger.warning(
                    "잔고 차이 %.1f%%: 실제=%.0f, DB 역산=%.0f → 미검증 거래 즉시 재보정",
                    diff_pct,
                    total_actual,
                    db_total,
                )
                # 자동 복구: 미검증 거래 재보정
                recon_result = self.reconcile_trades()
                corrected = recon_result.get("corrected", 0)

                if corrected > 0:
                    # 재보정 후 재확인
                    db_total_after = self._calculate_db_total_asset()
                    diff_pct_after = abs(total_actual - db_total_after) / total_actual * 100
                    logger.info(
                        "재보정 후 잔고 차이: %.1f%% → %.1f%% (%d건 보정)",
                        diff_pct,
                        diff_pct_after,
                        corrected,
                    )

                    if diff_pct_after > 2.0:
                        msg = (
                            f"잔고 차이 {diff_pct_after:.1f}%: "
                            f"실제={total_actual:,.0f}원, DB={db_total_after:,.0f}원 "
                            f"({corrected}건 보정 후)"
                        )
                        if self._notifier:
                            self._notifier.send(f"⚠️ *잔고 불일치 경고*\n{msg}")
                        return {"status": "warning", "message": msg, "diff_pct": diff_pct_after}

                    return {
                        "status": "ok",
                        "message": f"자동 보정 완료 ({corrected}건): {diff_pct:.1f}% → {diff_pct_after:.1f}%",
                        "krw_balance": actual_krw,
                        "total": total_actual,
                    }
                else:
                    msg = (
                        f"잔고 차이 {diff_pct:.1f}%: "
                        f"실제={total_actual:,.0f}원, DB={db_total:,.0f}원 (보정 가능 건 없음)"
                    )
                    if self._notifier:
                        self._notifier.send(f"⚠️ *잔고 불일치 경고*\n{msg}")
                    return {"status": "warning", "message": msg, "diff_pct": diff_pct}

            return {"status": "ok", "krw_balance": actual_krw, "coin_value": coin_value, "total": total_actual}
        except Exception as e:
            logger.error("잔고 일관성 체크 실패: %s", e)
            return {"status": "warning", "message": str(e)}

    def _calculate_db_total_asset(self) -> float:
        """DB 기록 기준 총자산을 역산한다."""
        try:
            import pyupbit

            # 매도 수익 합산
            row = self._db.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN side = 'sell' THEN total_krw - fee_krw ELSE 0 END), 0)
                    - COALESCE(SUM(CASE WHEN side = 'buy' THEN total_krw ELSE 0 END), 0)
                    AS net_flow
                FROM trades
                """
            ).fetchone()
            net_flow = row[0] if row else 0

            # 미매도 코인 DB 기록 가치
            active_rows = self._db.execute(
                """
                SELECT coin, amount FROM trades t
                WHERE side = 'buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
                """
            ).fetchall()
            db_coin_value = 0
            for ar in active_rows:
                ad = dict(ar)
                cp = pyupbit.get_current_price(ad["coin"])
                if cp:
                    db_coin_value += ad["amount"] * cp

            # 최초 입금액이 없으므로 daily_reports의 starting_balance 참고
            first_report = self._db.execute(
                "SELECT starting_balance_krw FROM daily_reports ORDER BY date ASC LIMIT 1"
            ).fetchone()
            initial_balance = dict(first_report)["starting_balance_krw"] if first_report else 0

            return initial_balance + net_flow + db_coin_value
        except Exception as e:
            logger.error("DB 총자산 역산 실패: %s", e)
            return 0

    def _send_alert(self, results: dict) -> None:
        """이상 발견 시 Slack 알림."""
        lines = ["⚠️ *일일 헬스체크 이상 발견*\n"]
        for key in results.get("issues", []):
            detail = results.get(key, {})
            msg = detail.get("message", "상세 정보 없음")
            lines.append(f"• *{key}*: {msg}")

        self._notifier.send("\n".join(lines))
