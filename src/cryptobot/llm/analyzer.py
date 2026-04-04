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

# 분석 프롬프트
ANALYSIS_PROMPT = """당신은 암호화폐 시장 분석 전문가입니다. 아래 데이터를 분석하여 JSON으로 응답하세요.

## 최근 뉴스 (최근 4시간)
{news_text}

## 공포/탐욕 지수
{fear_greed_text}

## 현재 시장 상태
{market_text}

## 최근 매매 성과
{performance_text}

## 사용 가능한 전략
- volatility_breakout: 변동성 돌파 (상승장에 유리, k_value 0.3~0.7)
- bb_rsi_combined: 볼린저+RSI 복합 (횡보/하락장에 유리, bb_std 1.0~2.5, rsi_oversold 25~40)
- rsi_mean_reversion: RSI 평균회귀 (횡보장, oversold 25~40)
- ma_crossover: 이동평균 교차 (추세 전환)
- bollinger_bands: 볼린저 밴드 (횡보장, bb_std 1.0~2.5)

## 요청

아래 JSON 형식으로 정확히 응답하세요. JSON 외 다른 텍스트를 포함하지 마세요.

```json
{{
  "market_summary_kr": "한국어 시장 요약 (3~5문장. 현재 상황, 주요 뉴스 영향, 단기 전망 포함)",
  "market_state": "bullish 또는 bearish 또는 sideways",
  "confidence": 0.0~1.0,
  "aggression": 0.0~1.0,
  "allow_trading": true 또는 false,
  "recommended_strategy": "전략 이름",
  "recommended_params": {{
    "k_value": 0.5,
    "bb_std": 1.5,
    "rsi_oversold": 35,
    "stop_loss_pct": -5.0,
    "trailing_stop_pct": -3.0
  }},
  "reasoning": "판단 근거 (한국어, 2~3문장)"
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

            # 2. 프롬프트 구성
            prompt = ANALYSIS_PROMPT.format(
                news_text=news_text,
                fear_greed_text=fear_greed_text,
                market_text=market_text,
                performance_text=performance_text,
            )

            # 3. LLM 호출
            result = self._call_claude(prompt)
            if result is None:
                return None

            # 4. 결과 저장
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

        self._db.execute(
            """
            INSERT INTO llm_decisions (
                timestamp, model,
                output_market_state, output_aggression, output_allow_trading,
                output_k_value, output_stop_loss, output_trailing_stop,
                output_reasoning,
                input_tokens, output_tokens, cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
