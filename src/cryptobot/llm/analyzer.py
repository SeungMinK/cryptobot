"""LLM 시장분석 모듈.

4시간마다 뉴스 + 시장 데이터를 Claude에 보내서:
1. 한국어 시장 요약
2. 시장 심리 판단
3. 전략 선택 권고
4. 파라미터 조절 권고
"""

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 하드 리밋 — LLM이 이 범위를 벗어나면 클리핑
HARD_LIMITS = {
    "stop_loss_pct": (-20.0, -5.0),
    "trailing_stop_pct": (-10.0, -1.0),
    "max_position_per_coin_pct": (30.0, 70.0),
    "max_coins": (3, 10),
    "min_balance_pct": (5.0, 10.0),  # 원금 대비 최소 유지 %
    "k_value": (0.2, 0.8),
    "bb_std": (0.8, 2.5),
    "rsi_oversold": (20, 45),
    "aggression": (0.1, 1.0),
}

# 분석 프롬프트
ANALYSIS_PROMPT = """당신은 암호화폐 자동매매 봇의 시장 분석 전문가입니다.
아래 데이터를 종합 분석하여 매매 전략과 파라미터를 조절하세요.

## 최근 뉴스 (최근 4시간)
{news_text}

## 공포/탐욕 지수
{fear_greed_text}

## 현재 시장 상태
{market_text}

## 현재 잔고 및 포지션
{balance_text}

## 최근 매매 성과
{performance_text}

## 이전 분석 결과 피드백
{previous_feedback}

## 사용 가능한 전략
- volatility_breakout: 변동성 돌파 (상승장, k_value 0.2~0.8)
- bb_rsi_combined: 볼린저+RSI 복합 (횡보/하락장, bb_std 0.8~2.5, rsi_oversold 20~45)
- rsi_mean_reversion: RSI 평균회귀 (횡보장, oversold 20~45)
- ma_crossover: 이동평균 교차 (추세 전환)
- bollinger_bands: 볼린저 밴드 (횡보장, bb_std 0.8~2.5)

## 조절 가능 범위 (하드 리밋)
- 손절: -20% ~ -5%
- 트레일링 스탑: -10% ~ -1%
- 종목당 최대 포지션: 30% ~ 70%
- 모니터링 코인 수: 3 ~ 10개
- 최소 유지 잔고: 원금의 5% ~ 10%

## 과거 파라미터별 성과
{param_stats_text}

## 중요 규칙
- 업비트 현물 거래만 가능 (숏/선물/레버리지 불가)
- 하락장에서는 "안 사는 것"이 최선 → aggression 낮추고, rsi_oversold 낮추고, max_coins 줄이기
- 공포/탐욕 지수 25 이하(극도 공포)는 역사적으로 매수 적기 (7년 백테스트 1,145% 수익). 공포 구간에서 aggression을 오히려 높이는 역발상을 고려하세요. 단, 손절은 반드시 유지.
- allow_trading은 항상 true로 유지 (매매 중단은 사람이 결정)
- 시장이 극도로 위험하다고 판단되면 should_alert_stop을 true로 설정
- 코인 추가/제거 시 이유를 명시
- 과거 파라미터 성과 데이터가 충분하면(50건+) 적극 참고, 부족하면 참고만

## 요청

아래 JSON 형식으로 정확히 응답하세요. JSON 외 다른 텍스트를 포함하지 마세요.

```json
{{
  "market_summary_kr": "한국어 시장 요약 (3~5문장)",
  "market_state": "bullish/bearish/sideways",
  "confidence": 0.0~1.0,
  "aggression": 0.1~1.0,
  "should_alert_stop": false,
  "alert_message": "매수 중단 권장 사유 (should_alert_stop이 true일 때만)",
  "recommended_strategy": "전략 이름",
  "recommended_params": {{
    "k_value": 0.5,
    "bb_std": 1.5,
    "rsi_oversold": 35,
    "stop_loss_pct": -5.0,
    "trailing_stop_pct": -3.0,
    "max_position_per_coin_pct": 50,
    "max_coins": 5
  }},
  "coin_recommendations": {{
    "add": ["KRW-SOL", "KRW-DOGE"],
    "remove": ["KRW-NEO"],
    "reasons": "추가/제거 사유"
  }},
  "reasoning": "전체 판단 근거 (한국어, 2~3문장)"
}}
```"""


class LLMAnalyzer:
    """LLM 시장 분석기."""

    def __init__(self, db) -> None:
        self._db = db
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._model = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    # Haiku 4.5 가격 (2026-04 기준)
    PRICE_INPUT_PER_M = 0.80   # $0.80 / 1M 입력 토큰
    PRICE_OUTPUT_PER_M = 4.00  # $4.00 / 1M 출력 토큰
    MIN_INTERVAL_HOURS = 4

    def _should_run(self) -> bool:
        """마지막 분석으로부터 4시간 이상 지났는지 확인."""
        row = self._db.execute(
            "SELECT timestamp FROM llm_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return True

        last = datetime.fromisoformat(dict(row)["timestamp"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds() / 3600
        if elapsed < self.MIN_INTERVAL_HOURS:
            logger.info("LLM 분석 스킵: 마지막 분석 %.1f시간 전 (최소 %d시간)", elapsed, self.MIN_INTERVAL_HOURS)
            return False
        return True

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        """토큰 → USD 비용 계산."""
        return round(
            input_tokens / 1_000_000 * self.PRICE_INPUT_PER_M +
            output_tokens / 1_000_000 * self.PRICE_OUTPUT_PER_M,
            6,
        )

    def analyze(self) -> dict | None:
        """시장 분석 실행. 뉴스 + 시장 데이터 → LLM → 결과 저장."""
        if not self.is_configured:
            logger.warning("LLM API 키 미설정 — 분석 스킵")
            return None

        if not self._should_run():
            return None

        try:
            # 1. 입력 데이터 수집
            news_text = self._get_news_text()
            fear_greed_text = self._get_fear_greed_text()
            market_text = self._get_market_text()
            performance_text = self._get_performance_text()

            balance_text = self._get_balance_text()
            previous_feedback = self._get_previous_feedback()
            param_stats_text = self._get_param_stats_text()

            # 2. 프롬프트 구성
            prompt = ANALYSIS_PROMPT.format(
                news_text=news_text,
                fear_greed_text=fear_greed_text,
                market_text=market_text,
                balance_text=balance_text,
                performance_text=performance_text,
                previous_feedback=previous_feedback,
                param_stats_text=param_stats_text,
            )

            # 2.5. 프롬프트 버전 저장
            prompt_version_id = self._ensure_prompt_version(prompt)

            # 3. LLM 호출
            result = self._call_claude(prompt)
            if result is None:
                return None

            result["_prompt_version_id"] = prompt_version_id

            # 4. 하드 리밋 적용 + 안전장치
            result = self._apply_hard_limits(result)

            # 매수 중단 경고 (Slack)
            if result.get("should_alert_stop"):
                self._send_stop_alert(result.get("alert_message", "시장 위험 감지"))

            # allow_trading 강제 true (사람만 제어)
            result["allow_trading"] = True

            # 5. 결과 저장
            self._save_decision(result)

            # 5. 파라미터 적용
            self._apply_recommendations(result)

            logger.info(
                "LLM 분석 완료: %s | 전략=%s | 공격성=%.1f",
                result.get("market_state", "?"),
                result.get("recommended_strategy", "?"),
                result.get("aggression", 0),
            )
            return result

        except Exception as e:
            logger.error("LLM 분석 실패: %s", e, exc_info=True)
            return None

    def _apply_hard_limits(self, result: dict) -> dict:
        """LLM 응답에 하드 리밋 클리핑."""
        params = result.get("recommended_params", {})

        for key, (mn, mx) in HARD_LIMITS.items():
            if key in params:
                original = params[key]
                params[key] = max(mn, min(mx, params[key]))
                if params[key] != original:
                    logger.warning("하드 리밋 클리핑: %s = %s → %s", key, original, params[key])

        # aggression도 클리핑
        if "aggression" in result:
            mn, mx = HARD_LIMITS["aggression"]
            result["aggression"] = max(mn, min(mx, result["aggression"]))

        result["recommended_params"] = params
        return result

    def _send_stop_alert(self, message: str) -> None:
        """매수 중단 권고 Slack 알림."""
        from cryptobot.notifier.slack import SlackNotifier
        notifier = SlackNotifier()
        notifier.send(f"🚨 *LLM 매수 중단 권고*\n{message}\n\n매매를 중단하려면 Admin 설정에서 '매매 허용'을 OFF로 변경하세요.")

    def _get_balance_text(self) -> str:
        """현재 잔고 + 포지션 정보."""
        try:
            from cryptobot.bot.trader import Trader
            trader = Trader()
            if not trader.is_ready:
                return "API 키 미설정"

            krw = trader.get_balance_krw()

            # 보유 코인
            held = self._db.execute('''
                SELECT coin, price, amount, total_krw FROM trades t
                WHERE side = 'buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
            ''').fetchall()

            lines = [f"KRW 잔고: {krw:,.0f}원"]
            total_coin = 0
            for h in held:
                h = dict(h)
                try:
                    import pyupbit
                    cp = pyupbit.get_current_price(h["coin"])
                    val = h["amount"] * cp if cp else h["total_krw"]
                    total_coin += val
                    lines.append(f"  {h['coin'].replace('KRW-','')}: 투자 {h['total_krw']:,.0f} → 평가 {val:,.0f}")
                except Exception:
                    total_coin += h["total_krw"]

            lines.append(f"총 자산: {krw + total_coin:,.0f}원")
            lines.append(f"최소 주문: 5,000원")
            lines.append(f"신규 매수 가능: {max(0, krw - 10000):,.0f}원")
            return "\n".join(lines)
        except Exception as e:
            return f"잔고 조회 실패: {e}"

    def _get_previous_feedback(self) -> str:
        """이전 LLM 분석의 성과 피드백."""
        prev = self._db.execute(
            "SELECT * FROM llm_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if prev is None:
            return "첫 분석 (이전 기록 없음)"

        p = dict(prev)
        pnl = p.get("evaluation_period_pnl_pct")
        was_good = p.get("evaluation_was_good")

        lines = [
            f"이전 분석: {p.get('timestamp', '?')}",
            f"추천 전략: {p.get('output_market_state', '?')}",
        ]
        if pnl is not None:
            lines.append(f"이전 권고 후 성과: {pnl:+,.0f}원 ({'좋았음' if was_good else '나빴음'})")
        else:
            lines.append("이전 권고 후 성과: 아직 평가 안 됨")

        # before/after 정보
        news_summary = p.get("input_news_summary")
        if news_summary:
            try:
                ba = json.loads(news_summary)
                if "before" in ba:
                    lines.append(f"이전 변경: {ba.get('before', {})} → {ba.get('after', {})}")
            except Exception:
                pass

        return "\n".join(lines)

    def _ensure_prompt_version(self, prompt: str) -> int:
        """현재 프롬프트를 DB에 저장하고 버전 ID 반환."""
        import hashlib
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]

        # 이미 같은 프롬프트가 활성화되어 있으면 그대로
        active = self._db.execute(
            "SELECT id, version FROM prompt_versions WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if active and dict(active)["version"].endswith(prompt_hash):
            return dict(active)["id"]

        # 기존 활성 비활성화
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        self._db.execute(
            "UPDATE prompt_versions SET is_active = FALSE, deactivated_at = ? WHERE is_active = TRUE",
            (now,),
        )

        # 새 버전 생성
        version_num = (self._db.execute("SELECT COUNT(*) FROM prompt_versions").fetchone()[0] or 0) + 1
        version = f"v{version_num}_{prompt_hash}"

        cursor = self._db.execute(
            """INSERT INTO prompt_versions (version, prompt_text, description, is_active, created_at, activated_at)
            VALUES (?, ?, ?, TRUE, ?, ?)""",
            (version, prompt, f"자동 생성 v{version_num}", now, now),
        )
        self._db.commit()
        prompt_id = cursor.lastrowid
        logger.info("프롬프트 버전 생성: %s (id=%d)", version, prompt_id)
        return prompt_id

    def _get_param_stats_text(self) -> str:
        """과거 파라미터별 성과 통계."""
        rows = self._db.execute(
            """
            SELECT strategy_params_json, strategy,
                   COUNT(*) as total,
                   SUM(CASE WHEN executed = TRUE THEN 1 ELSE 0 END) as executed_cnt
            FROM trade_signals
            WHERE strategy_params_json IS NOT NULL AND signal_type IN ('buy', 'sell')
            GROUP BY strategy_params_json, strategy
            ORDER BY total DESC
            LIMIT 10
            """
        ).fetchall()

        if not rows:
            return "과거 데이터 없음 (아직 충분한 매매 이력 없음)"

        # 매도 기준 승률 계산
        stats_rows = self._db.execute(
            """
            SELECT t.strategy,
                   COUNT(*) as sell_cnt,
                   SUM(CASE WHEN t.profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                   AVG(t.profit_krw) as avg_pnl
            FROM trades t
            WHERE t.side = 'sell'
            GROUP BY t.strategy
            """
        ).fetchall()

        lines = []
        for r in stats_rows:
            r = dict(r)
            win_rate = (r["wins"] or 0) / r["sell_cnt"] * 100 if r["sell_cnt"] > 0 else 0
            lines.append(
                f"  {r['strategy']}: {r['sell_cnt']}건 매도, 승률 {win_rate:.0f}%, 평균 손익 {r['avg_pnl'] or 0:+,.0f}원"
            )

        total_trades = sum(dict(r)["sell_cnt"] for r in stats_rows)
        reliability = "적극 참고" if total_trades >= 50 else "참고만 (데이터 부족)" if total_trades >= 10 else "매우 제한적"
        lines.insert(0, f"총 {total_trades}건 매도 — 신뢰도: {reliability}")

        return "\n".join(lines)

    def _get_news_text(self) -> str:
        """최근 4시간 뉴스를 텍스트로."""
        rows = self._db.execute(
            """
            SELECT title, summary, sentiment_keyword, coins_mentioned, source
            FROM news_articles
            WHERE collected_at >= datetime('now', '-4 hours')
            ORDER BY published_at DESC
            LIMIT 20
            """
        ).fetchall()

        if not rows:
            return "최근 4시간 뉴스 없음"

        lines = []
        for i, r in enumerate(rows, 1):
            r = dict(r)
            coins = f" [{r['coins_mentioned']}]" if r["coins_mentioned"] else ""
            lines.append(
                f"{i}. [{r['source']}] {r['title']}{coins} ({r['sentiment_keyword']})"
            )
            if r["summary"]:
                lines.append(f"   {r['summary'][:150]}")
        return "\n".join(lines)

    def _get_fear_greed_text(self) -> str:
        """Fear & Greed 최신값."""
        row = self._db.execute(
            "SELECT * FROM fear_greed_index ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            r = dict(row)
            return f"값: {r['value']} ({r['classification']}) — 측정시간: {r['timestamp']}"
        return "데이터 없음"

    def _get_market_text(self) -> str:
        """현재 시장 데이터."""
        rows = self._db.execute(
            """
            SELECT coin, price, rsi_14, ma_5, ma_20, market_state
            FROM market_snapshots
            WHERE id IN (SELECT MAX(id) FROM market_snapshots WHERE coin LIKE 'KRW-%' GROUP BY coin)
            """
        ).fetchall()

        lines = []
        for r in rows:
            r = dict(r)
            name = r["coin"].replace("KRW-", "")
            rsi = f"RSI={r['rsi_14']:.0f}" if r["rsi_14"] else ""
            state = r["market_state"] or "?"
            lines.append(f"{name}: {r['price']:,.0f}원 | {state} | {rsi}")
        return "\n".join(lines) if lines else "시장 데이터 없음"

    def _get_performance_text(self) -> str:
        """최근 매매 성과."""
        row = self._db.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN profit_krw <= 0 THEN 1 ELSE 0 END) as losses,
                SUM(profit_krw) as total_pnl
            FROM trades WHERE side = 'sell'
            AND timestamp >= datetime('now', '-24 hours')
            """
        ).fetchone()

        r = dict(row)
        if r["total"] == 0:
            return "최근 24시간 매매 없음"

        win_rate = (r["wins"] or 0) / r["total"] * 100 if r["total"] > 0 else 0
        return f"24시간: {r['total']}건 (승률 {win_rate:.0f}%, 손익 {r['total_pnl'] or 0:+,.0f}원)"

    def _call_claude(self, prompt: str) -> dict | None:
        """Claude API 호출."""
        import anthropic

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            content = response.content[0].text.strip()

            # JSON 파싱 (```json ... ``` 형태도 처리)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            # 토큰 사용량 기록
            result["_input_tokens"] = response.usage.input_tokens
            result["_output_tokens"] = response.usage.output_tokens
            result["_model"] = self._model

            logger.info(
                "Claude 응답: %d input + %d output 토큰",
                response.usage.input_tokens,
                response.usage.output_tokens,
            )
            return result

        except Exception as e:
            logger.error("Claude API 호출 실패: %s", e)
            return None

    def _save_decision(self, result: dict) -> None:
        """분석 결과를 llm_decisions 테이블에 저장."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        params = result.get("recommended_params", {})

        input_tokens = result.get("_input_tokens", 0)
        output_tokens = result.get("_output_tokens", 0)
        cost = self._calc_cost(input_tokens, output_tokens)

        prompt_vid = result.get("_prompt_version_id")

        self._db.execute(
            """
            INSERT INTO llm_decisions (
                timestamp, model,
                output_market_state, output_aggression, output_allow_trading,
                output_k_value, output_stop_loss, output_trailing_stop,
                output_reasoning,
                input_tokens, output_tokens, cost_usd,
                input_market_snapshot_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                now,
                result.get("_model", self._model),
                result.get("market_state"),
                result.get("aggression"),
                result.get("allow_trading", True),
                params.get("k_value"),
                params.get("stop_loss_pct"),
                params.get("trailing_stop_pct"),
                result.get("market_summary_kr", "") + "\n\n" + result.get("reasoning", ""),
                input_tokens,
                output_tokens,
                cost,
                prompt_vid,
            ),
        )
        self._db.commit()
        logger.info("LLM 비용: $%.4f (입력 %d + 출력 %d 토큰)", cost, input_tokens, output_tokens)

    def _evaluate_previous(self) -> None:
        """이전 LLM 분석의 성과를 평가하여 기록."""
        prev = self._db.execute(
            "SELECT id, timestamp FROM llm_decisions ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if prev is None:
            return

        prev = dict(prev)
        # 이전 분석 이후 매매 성과
        row = self._db.execute(
            """
            SELECT
                COUNT(*) as trades,
                SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                SUM(profit_krw) as total_pnl
            FROM trades WHERE side = 'sell' AND timestamp >= ?
            """,
            (prev["timestamp"],),
        ).fetchone()
        r = dict(row)

        if r["trades"] and r["trades"] > 0:
            pnl = r["total_pnl"] or 0
            was_good = pnl > 0
            self._db.execute(
                "UPDATE llm_decisions SET evaluation_period_pnl_pct = ?, evaluation_was_good = ? WHERE id = ?",
                (round(pnl, 2), was_good, prev["id"]),
            )
            self._db.commit()
            logger.info("이전 LLM 성과: %d건 매매, PnL %+,.0f원, 판단 %s",
                        r["trades"], pnl, "good" if was_good else "bad")

    def _apply_recommendations(self, result: dict) -> None:
        """LLM 권고를 bot_config에 반영. before/after 스냅샷 기록."""
        params = result.get("recommended_params", {})
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 이전 성과 평가
        self._evaluate_previous()

        # before 스냅샷
        before = {}
        config_keys = ["stop_loss_pct", "trailing_stop_pct", "k_value", "allow_trading"]
        for key in config_keys:
            row = self._db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
            if row:
                before[key] = dict(row)["value"]

        # 파라미터 적용
        config_map = {
            "stop_loss_pct": params.get("stop_loss_pct"),
            "trailing_stop_pct": params.get("trailing_stop_pct"),
            "k_value": params.get("k_value"),
            "max_position_per_coin_pct": params.get("max_position_per_coin_pct"),
            "max_coins": params.get("max_coins"),
        }

        for key, value in config_map.items():
            if value is not None:
                self._db.execute(
                    "UPDATE bot_config SET value = ?, updated_at = ? WHERE key = ?",
                    (str(value), now, key),
                )

        if result.get("allow_trading") is not None:
            self._db.execute(
                "UPDATE bot_config SET value = ?, updated_at = ? WHERE key = 'allow_trading'",
                (str(result["allow_trading"]).lower(), now),
            )

        # 전략 파라미터 반영
        strategy = result.get("recommended_strategy")
        if strategy:
            strategy_params = {}
            if params.get("bb_std"):
                strategy_params["bb_std"] = params["bb_std"]
                strategy_params["bb_period"] = 20
            if params.get("rsi_oversold"):
                strategy_params["rsi_oversold"] = params["rsi_oversold"]
                strategy_params["rsi_period"] = 14
                strategy_params["rsi_overbought"] = 50
            if params.get("k_value"):
                strategy_params["k_value"] = params["k_value"]

            if strategy_params:
                self._db.execute(
                    "UPDATE strategies SET default_params_json = ?, updated_at = ? WHERE name = ?",
                    (json.dumps(strategy_params), now, strategy),
                )

        # after 스냅샷
        after = {k: str(v) for k, v in config_map.items() if v is not None}
        if result.get("allow_trading") is not None:
            after["allow_trading"] = str(result["allow_trading"]).lower()

        # before/after를 최신 llm_decisions에 기록
        self._db.execute(
            """
            UPDATE llm_decisions SET
                input_news_summary = ?
            WHERE id = (SELECT MAX(id) FROM llm_decisions)
            """,
            (json.dumps({"before": before, "after": after, "strategy": strategy}, ensure_ascii=False),),
        )

        self._db.commit()
        changes = {k: f"{before.get(k, '?')} → {v}" for k, v in after.items()}
        logger.info("LLM 권고 적용: %s", changes)
