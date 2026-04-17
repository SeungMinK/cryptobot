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

# 공통 파라미터 키 — 전략별 파라미터가 아닌 bot_config에 직접 적용되는 키
COMMON_PARAM_KEYS = {
    "stop_loss_pct",
    "trailing_stop_pct",
    "max_position_per_coin_pct",
    "max_spread_pct",
    "emergency_held_pct",
    "emergency_non_held_pct",
    "roi_10min",
    "roi_30min",
    "roi_60min",
    "roi_120min",
}

# 하드 리밋 — LLM이 이 범위를 벗어나면 클리핑
HARD_LIMITS = {
    "stop_loss_pct": (-20.0, -5.0),
    "trailing_stop_pct": (-10.0, -1.0),
    "max_position_per_coin_pct": (30.0, 80.0),
    "min_balance_pct": (5.0, 10.0),  # 원금 대비 최소 유지 %
    "k_value": (0.2, 0.8),
    "bb_std": (0.8, 2.5),
    "rsi_oversold": (20, 45),
    "aggression": (0.1, 1.0),
    "roi_10min": (1.0, 5.0),
    "roi_30min": (0.5, 3.0),
    "roi_60min": (0.3, 2.0),
    "roi_120min": (0.1, 1.0),
    "max_spread_pct": (0.1, 1.0),
    "emergency_held_pct": (1.0, 10.0),
    "emergency_non_held_pct": (3.0, 15.0),
}

# 분석 프롬프트
ANALYSIS_PROMPT = """당신은 암호화폐 자동매매 봇의 시장 분석 전문가입니다.
아래 데이터를 종합 분석하여 매매 전략과 파라미터를 조절하세요.

## 최근 뉴스 (마지막 분석 이후)
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

## 현재 전략 파라미터 (지금 봇에 적용 중인 값)
{current_strategy_params}

## 현재 활성 전략
{active_strategy_text}

## 사용 가능한 전략
{strategies_text}

## 공통 파라미터 조절 범위 (하드 리밋)
| 파라미터 | 범위 | 설명 |
|----------|------|------|
| stop_loss_pct | -20.0 ~ -5.0 | 손절률 (%) |
| trailing_stop_pct | -10.0 ~ -1.0 | 트레일링 스탑 (%) |
| max_position_per_coin_pct | 30 ~ 80 | 종목당 최대 포지션 (%) |
| roi_10min | 1.0 ~ 5.0 | 10분 보유 시 목표 수익률 (%) |
| roi_30min | 0.5 ~ 3.0 | 30분 보유 시 목표 수익률 (%) |
| roi_60min | 0.3 ~ 2.0 | 60분 보유 시 목표 수익률 (%) |
| roi_120min | 0.1 ~ 1.0 | 120분 보유 시 목표 수익률 (%) — 손익비 개선 핵심 |
| max_spread_pct | 0.1 ~ 1.0 | 호가 스프레드 필터 (%) — 이 이상이면 스캐너에서 제외 |

## 과거 전략별 실제 성과
{param_stats_text}

## 백테스트 시뮬레이션 결과 (파라미터 스윕 포함, 코인당 수익률 Top 10)
{backtest_text}

위 백테스트는 실제 OHLCV 일봉 데이터로 각 전략의 다양한 파라미터 조합을 시뮬레이션한 결과입니다.
괄호 안은 해당 결과의 핵심 파라미터입니다.
현재 파라미터와 비교하여 조정 근거로 활용하세요.
단, 백테스트는 과거 데이터 기반이므로 맹신하지 말고 참고 자료로만 사용하세요.

## 중요 규칙

### 매매 로직 이해 (필수)
- bb_rsi_combined 매수 조건: **RSI ≤ rsi_oversold AND 가격 < 볼린저 하단** (두 조건 동시 충족 필요)
- 현재 코인들의 RSI를 확인하고, rsi_oversold를 적절히 조절하세요
- 예: 코인 RSI가 33인데 rsi_oversold=30이면 매수 불가 → rsi_oversold=35로 올리면 매수 가능
- bb_std를 낮추면 볼린저 밴드가 좁아져 하단 이탈이 쉬워짐 (매수 기회 증가)

### 핵심 목표: 자산 성장 (승률보다 손익비!)
- **승률보다 손익비가 중요합니다** — 70% 이겨도 1번 질 때 크게 지면 의미 없음
- 손익비 = 평균 승(%) ÷ 평균 패(%) → **1.5 이상을 목표**, 최소 1.0 초과 유지
- 성과 섹션의 "손익비 X.XX"가 목표 미달이면 ROI 상향 또는 stop_loss 조정을 적극 검토
- 현재 보유 포지션의 손익을 확인하고, 손절/ROI 기준을 적극 조절하세요

### 파라미터 조절 핵심 가이드
1. **ROI 테이블** — 이길 때 크게 이기는 핵심
   - roi_60min: 이 값이 높을수록 더 오래 보유 → 건당 수익 증가
   - roi_120min: 최소 탈출선 — 너무 낮으면 본전치기 매도 발생
   - 손절(-5%)이면 roi_60min은 최소 +1.5% 이상 (1:3 비율)
   - 시장 변동성에 맞춰 매 분석마다 조절하세요

2. **rsi_oversold** — 매수 기회 조절
   - 현재 코인 RSI를 확인 후 적절히 설정 (RSI 근처보다 약간 위)
   - 공포장: 올려서 매수 기회 확보 / 안정장: 내려서 신중 진입

3. **bb_std** — 볼린저 밴드 폭
   - 낮추면 매수 쉬움 (밴드 좁음) / 높이면 매수 어려움 (밴드 넓음)

4. **stop_loss_pct** — 한 번 질 때의 크기
   - 좁으면: 자주 손절 → 승률↓ 손실↓ / 넓으면: 가끔 손절 → 승률↑ 손실↑
   - ROI와 균형 맞추기 (손절 -5%면 ROI 최소 +1.5%)

### 성과 해석 주의
- 전체 승률이 아닌 **전략별 승률**을 보세요
- 나쁜 전략의 과거 성과 때문에 좋은 전략의 파라미터를 보수적으로 잡지 마세요
- **건당 평균 수익이 건당 평균 손실의 1/3 이상인지 확인하세요**

### 전략 전환 판단 (매 분석마다 반드시 수행)
**주의: 이 섹션은 단순 참고가 아니라 매 분석마다 반드시 수행해야 하는 핵심 작업입니다.**

1. **현재 전략 적합성 평가**: 위의 '현재 활성 전략' 정보와 '현재 시장 상태'를 비교하세요.
   - 현재 전략의 '적합 시장'과 실제 시장 상태가 불일치하면 전략 전환을 적극 검토
   - 예: 시장이 bullish인데 활성 전략이 bb_rsi_combined(sideways,bearish용)이면 → 전환 검토

2. **전환 판단 시 종합적으로 고려할 요소**:
   - 시장 상태(bullish/sideways/bearish)와 각 전략의 적합 시장
   - 현재 코인 보유 현황과 미실현 손익
   - 백테스트 시뮬레이션 결과(해당 전략의 수익률, 승률, MDD)
   - 최근 매매 성과(현재 전략의 실전 승률, 손익비)
   - 공포/탐욕 지수 추이

3. **전환 실행 방법**: 전략을 바꾸기로 결정했다면:
   - recommended_strategy에 새 전략 이름 설정
   - recommended_params에 해당 전략의 파라미터 포함
   - reasoning에 전환 근거 명시

4. **전략 유지도 적극적 판단**: 현재 전략이 시장에 맞다면 유지하되,
   "관성으로 유지"가 아니라 "검토 후 유지"임을 reasoning에 명시

### 시장 대응
- 업비트 현물 거래만 가능 (숏/선물/레버리지 불가)
- 공포/탐욕 지수 25 이하(극도 공포): 과거 평균 수익은 높았으나 **단기 추가 하락 위험도 공존**.
  분할 진입/포지션 축소로 대응하고, 한 방향 확신은 금물
- 공포 심화 시 선택지: aggression을 과도하게 올리지 말고,
  rsi_oversold/bb_std를 조절해 "매수 조건 완화"와 "신중한 진입"을
  시장 추세(bearish 지속 vs 반등 신호)에 맞춰 결정
- allow_trading은 항상 true (매매 중단은 사람이 결정)
- should_alert_stop = true 조건 (아래 중 하나 이상 해당 시):
  - 공포/탐욕 지수 10 이하 + BTC 24h 변동 -10% 이상
  - 보유 포지션 평균 미실현 -10% 이상이면서 시장 전반 bearish
  - 거시 충격 뉴스(주요국 금융 시스템/대형 거래소 지급불능/규제 급변 등)가 다수 보도
  - 그 외 "사람이 당장 봐야 할 수준"이라 판단되는 이례적 상황

## 응답 형식

아래 JSON 형식으로 **정확히** 응답하세요. JSON 외 다른 텍스트를 포함하지 마세요.
**recommended_params의 모든 필드를 반드시 포함하세요. 하나라도 생략하지 마세요.**

```json
{{
  "market_summary_kr": "한국어 시장 요약 (3~5문장)",
  "market_state": "bullish/bearish/sideways",
  "confidence": 0.0~1.0,
  "aggression": 0.1~1.0,
  "should_alert_stop": false,
  "alert_message": "",
  "recommended_strategy": "전략 이름",
  "recommended_params": {{
    // 공통 파라미터 (모든 전략)
    "stop_loss_pct": -5.0,
    "trailing_stop_pct": -3.0,
    "max_position_per_coin_pct": 50,
    "roi_10min": 3.0,
    "roi_30min": 2.0,
    "roi_60min": 1.0,
    "roi_120min": 0.3,
    // 전략별 파라미터 — recommended_strategy에 해당하는 것만 포함
    // volatility_breakout: k_value
    // bb_rsi_combined: bb_std, rsi_oversold, bb_period, rsi_period
    // rsi_mean_reversion: rsi_period, oversold, overbought
    // ma_crossover: short_period, long_period
    // bollinger_bands: bb_period, bb_std
    // macd: fast, slow, signal_period
    // supertrend: st_period, st_multiplier
    // bollinger_squeeze: bb_period, bb_std, squeeze_lookback
    // breakout_momentum: entry_period, exit_period
    // grid_trading: grid_count, range_pct
  }},
  "coin_recommendations": {{
    "add": [],
    "remove": [],
    "reasons": "추가/제거 사유"
  }},
  "reasoning": "전체 판단 근거 (한국어, 2~3문장)"
}}
```"""

# 재시도 프롬프트 — 누락 필드 요청
RETRY_PROMPT = """이전 응답에서 recommended_params에 다음 필드가 누락되었습니다: {missing_fields}

모든 필드를 포함하여 다시 recommended_params만 JSON으로 응답하세요.
현재 시장 RSI 상황과 볼린저밴드 위치를 고려하여 적절한 값을 설정하세요.

```json
{{
  "recommended_params": {{
    "k_value": 0.5,
    "bb_std": 1.5,
    "rsi_oversold": 35,
    "stop_loss_pct": -5.0,
    "trailing_stop_pct": -3.0,
    "max_position_per_coin_pct": 50
  }}
}}
```"""


class LLMAnalyzer:
    """LLM 시장 분석기."""

    def __init__(self, db) -> None:
        self._db = db
        self._api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self._model = os.getenv("LLM_MODEL", "claude-haiku-4-5-20251001")

    def _get_config_float(self, key: str, default: float) -> float:
        """bot_config에서 float 값 조회."""
        row = self._db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
        if row:
            try:
                return float(dict(row)["value"])
            except (ValueError, TypeError):
                pass
        return default

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    # Haiku 4.5 가격 (2026-04 기준)
    PRICE_INPUT_PER_M = 0.80  # $0.80 / 1M 입력 토큰
    PRICE_OUTPUT_PER_M = 4.00  # $4.00 / 1M 출력 토큰
    MAX_DAILY_CALLS = 36  # 하드 리밋 (활발 시 24회 + 긴급 여유)
    # 동적 주기 (시장 활동량에 따라)
    INTERVAL_ACTIVE_MIN = 60  # 활발: 1시간 (30분은 파라미터 진동만 유발)
    INTERVAL_NORMAL_MIN = 120  # 보통: 2시간
    INTERVAL_QUIET_MIN = 240  # 한산: 4시간

    def _get_dynamic_interval_minutes(self) -> int:
        """시장 활동량에 따른 LLM 호출 간격(분) 결정.

        뉴스 건수는 ACTIVE 판정 기준에서 제외한다. 수집기 기본 출력이 시간당
        평균 3.8건이라 news_count>=3 조건이 57% 시간대에서 오판정의 주범이었고,
        뉴스發 시장 급변은 check_emergency()가 가격 기준으로 별도 포착한다.
        """
        # 최근 1시간 매매 건수
        trade_count = (
            self._db.execute("SELECT COUNT(*) FROM trades WHERE timestamp >= datetime('now', '-1 hour')").fetchone()[0]
            or 0
        )

        # 보유 포지션 수
        position_count = (
            self._db.execute(
                """SELECT COUNT(*) FROM trades t WHERE side='buy'
            AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side='sell')"""
            ).fetchone()[0]
            or 0
        )

        # 활발: 매매 2건+ OR 포지션 3개+
        if trade_count >= 2 or position_count >= 3:
            return self.INTERVAL_ACTIVE_MIN

        # 한산: 매매 0건 AND 포지션 0개
        if trade_count == 0 and position_count == 0:
            return self.INTERVAL_QUIET_MIN

        return self.INTERVAL_NORMAL_MIN

    def _should_run(self, force: bool = False) -> bool:
        """분석 실행 여부 판단 (동적 주기)."""
        # 일일 호출 제한
        daily_count = (
            self._db.execute("SELECT COUNT(*) FROM llm_decisions WHERE DATE(timestamp) = DATE('now')").fetchone()[0]
            or 0
        )
        if daily_count >= self.MAX_DAILY_CALLS:
            logger.warning("LLM 일일 호출 제한 도달: %d/%d", daily_count, self.MAX_DAILY_CALLS)
            return False

        # 강제 실행 (시장 급변)
        if force:
            logger.info("LLM 즉시 분석 (시장 급변 감지)")
            return True

        # 동적 간격 체크
        row = self._db.execute("SELECT timestamp FROM llm_decisions ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return True

        last = datetime.fromisoformat(dict(row)["timestamp"])
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        elapsed_min = (datetime.now(timezone.utc) - last).total_seconds() / 60
        interval = self._get_dynamic_interval_minutes()

        if elapsed_min < interval:
            logger.info("LLM 스킵: %.0f분 전 (다음: %d분 간격)", elapsed_min, interval)
            return False

        logger.info("LLM 분석 실행: %.0f분 경과 (%d분 간격, 활동 기반)", elapsed_min, interval)
        return True

    def check_emergency(self) -> bool:
        """시장 급변 감지 — 동적 기준 (보유 코인은 낮은 기준, 비보유는 높은 기준)."""
        try:
            # 보유 코인 목록
            held_rows = self._db.execute(
                """SELECT DISTINCT coin FROM trades t WHERE side='buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side='sell')"""
            ).fetchall()
            held_coins = {dict(r)["coin"] for r in held_rows}

            rows = self._db.execute(
                """
                SELECT m1.coin, m1.price as now_price, m2.price as prev_price
                FROM market_snapshots m1
                JOIN (
                    SELECT coin, price FROM market_snapshots
                    WHERE timestamp <= datetime('now', '-1 hour')
                    AND id IN (SELECT MAX(id) FROM market_snapshots
                               WHERE timestamp <= datetime('now', '-1 hour') GROUP BY coin)
                ) m2 ON m1.coin = m2.coin
                WHERE m1.id IN (SELECT MAX(id) FROM market_snapshots GROUP BY coin)
                AND m2.price > 0
                """
            ).fetchall()

            for r in rows:
                d = dict(r)
                change = abs(d["now_price"] - d["prev_price"]) / d["prev_price"] * 100
                # 보유 코인: 낮은 기준 (손절 관련) / 비보유: 높은 기준 (기회 포착)
                held_th = self._get_config_float("emergency_held_pct", 3.0)
                non_held_th = self._get_config_float("emergency_non_held_pct", 7.0)
                threshold = held_th if d["coin"] in held_coins else non_held_th
                if change >= threshold:
                    logger.warning(
                        "시장 급변 감지: %s %.1f%% 변동 (기준 %.0f%%, %s)",
                        d["coin"],
                        change,
                        threshold,
                        "보유" if d["coin"] in held_coins else "비보유",
                    )
                    return True
            return False
        except Exception as e:
            logger.debug("급변 감지 실패: %s", e)
            return False

    def _calc_cost(self, input_tokens: int, output_tokens: int) -> float:
        """토큰 → USD 비용 계산."""
        return round(
            input_tokens / 1_000_000 * self.PRICE_INPUT_PER_M + output_tokens / 1_000_000 * self.PRICE_OUTPUT_PER_M,
            6,
        )

    def analyze(self, force: bool = False) -> dict | None:
        """시장 분석 실행. 뉴스 + 시장 데이터 → LLM → 결과 저장."""
        if not self.is_configured:
            logger.warning("LLM API 키 미설정 — 분석 스킵")
            return None

        if not self._should_run(force=force):
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
            current_strategy_params = self._get_current_strategy_params()
            backtest_text, _backtest_run_date = self._get_backtest_text()

            # 2. 프롬프트 구성
            strategies_text = self._get_strategies_text()
            active_strategy_text = self._get_active_strategy_text()

            prompt = ANALYSIS_PROMPT.format(
                news_text=news_text,
                fear_greed_text=fear_greed_text,
                market_text=market_text,
                balance_text=balance_text,
                performance_text=performance_text,
                previous_feedback=previous_feedback,
                param_stats_text=param_stats_text,
                current_strategy_params=current_strategy_params,
                backtest_text=backtest_text,
                strategies_text=strategies_text,
                active_strategy_text=active_strategy_text,
            )

            # 2.5. 프롬프트 버전 저장
            prompt_version_id = self._ensure_prompt_version(prompt)

            # 3. LLM 호출
            result = self._call_claude(prompt)
            if result is None:
                return None

            # 3.5. 누락된 전략 파라미터 재시도
            result = self._retry_missing_params(result)

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
        notifier.send(
            f"🚨 *LLM 매수 중단 권고*\n{message}\n\n매매를 중단하려면 Admin 설정에서 '매매 허용'을 OFF로 변경하세요."
        )

    def _retry_missing_params(self, result: dict) -> dict:
        """LLM 응답에서 필수 전략 파라미터가 누락되면 1회 재시도."""
        params = result.get("recommended_params", {})
        missing = [k for k in self.REQUIRED_PARAMS if k not in params]

        if not missing:
            return result

        logger.warning("LLM 응답에 전략 파라미터 누락: %s — 재시도", missing)

        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self._api_key)
            retry_prompt = RETRY_PROMPT.format(missing_fields=", ".join(missing))

            response = client.messages.create(
                model=self._model,
                max_tokens=512,
                messages=[{"role": "user", "content": retry_prompt}],
            )

            # 토큰 누적
            result["_input_tokens"] = result.get("_input_tokens", 0) + response.usage.input_tokens
            result["_output_tokens"] = result.get("_output_tokens", 0) + response.usage.output_tokens

            content = response.content[0].text.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            retry_result = json.loads(content)
            if not isinstance(retry_result, dict):
                retry_result = {}
            retry_params = retry_result.get("recommended_params", retry_result)

            # 누락된 필드만 채우기 (기존 값 유지)
            for key in missing:
                if key in retry_params:
                    params[key] = retry_params[key]
                    logger.info("재시도로 파라미터 복구: %s = %s", key, retry_params[key])

            result["recommended_params"] = params

        except Exception as e:
            logger.warning("파라미터 재시도 실패: %s — 기존 값 유지", e)

        return result

    def _get_balance_text(self) -> str:
        """현재 잔고 + 포지션 정보."""
        try:
            from cryptobot.bot.trader import Trader

            trader = Trader()
            if not trader.is_ready:
                return "API 키 미설정"

            krw = trader.get_balance_krw()

            # 보유 코인
            held = self._db.execute("""
                SELECT coin, price, amount, total_krw FROM trades t
                WHERE side = 'buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side = 'sell')
            """).fetchall()

            lines = [f"KRW 잔고: {krw:,.0f}원"]
            total_coin = 0
            for h in held:
                h = dict(h)
                try:
                    import pyupbit

                    cp = pyupbit.get_current_price(h["coin"])
                    val = h["amount"] * cp if cp else h["total_krw"]
                    total_coin += val
                    lines.append(f"  {h['coin'].replace('KRW-', '')}: 투자 {h['total_krw']:,.0f} → 평가 {val:,.0f}")
                except Exception:
                    total_coin += h["total_krw"]

            total_asset = krw + total_coin
            buyable = max(0, krw - 10000)
            lines.append(f"총 자산: {total_asset:,.0f}원")
            lines.append("최소 주문: 5,000원")
            lines.append(f"신규 매수 가능: {buyable:,.0f}원")

            # 동시 보유 가능 종목 수 — max_position_per_coin_pct 제약 반영.
            # 작은 자본에서는 이 값이 곧 LLM의 집중도/다각화 결정 범위.
            max_pos_pct = self._get_config_float("max_position_per_coin_pct", 50.0)
            if total_asset > 0 and max_pos_pct > 0:
                per_coin_cap = total_asset * max_pos_pct / 100
                already_held = len(held)
                remaining_slots = int(buyable // per_coin_cap) if per_coin_cap > 0 else 0
                lines.append(
                    f"동시 보유 가능: 최대 {already_held + remaining_slots}종목 "
                    f"(max_position_per_coin_pct={max_pos_pct:.0f}%, 남은 슬롯 {remaining_slots})"
                )
            return "\n".join(lines)
        except Exception as e:
            return f"잔고 조회 실패: {e}"

    def _get_previous_feedback(self) -> str:
        """최근 3건 LLM 분석 성과 피드백.

        매매가 있었으면 PnL 기반, 없었으면 동기간 BTC 가격 변화로 대체 평가.
        분석 간격에 매매 0건이어도 "미평가" 루프에 빠지지 않게 한다.
        """
        rows = self._db.execute("SELECT * FROM llm_decisions ORDER BY id DESC LIMIT 3").fetchall()
        if not rows:
            return "첫 분석 (이전 기록 없음)"

        lines = []
        for i, prev in enumerate(rows):
            p = dict(prev)
            pnl = p.get("evaluation_period_pnl_pct")
            was_good = p.get("evaluation_was_good")
            label = "직전" if i == 0 else f"{i + 1}회 전"

            entry = f"[{label}] {p.get('timestamp', '?')} | {p.get('output_market_state', '?')}"
            if pnl is not None:
                entry += f" | 성과: {pnl:+,.0f}원 ({'좋았음' if was_good else '나빴음'})"
            else:
                # 매매가 없었으면 동기간 BTC 변화 + 매매 건수를 대체 지표로 표시
                proxy = self._get_feedback_proxy(p.get("timestamp"))
                entry += f" | {proxy}"

            # before/after 변경 요약
            news_summary = p.get("input_news_summary")
            if news_summary:
                try:
                    ba = json.loads(news_summary)
                    after = ba.get("after", {})
                    changed = [f"{k}={v}" for k, v in after.items()]
                    if changed:
                        entry += f" | 설정: {', '.join(changed[:5])}"
                except Exception:
                    pass

            lines.append(entry)

        return "\n".join(lines)

    def _get_feedback_proxy(self, since_ts: str | None) -> str:
        """매매 없는 구간의 대체 평가 지표.

        해당 분석 이후:
        - 매매 건수
        - BTC 현물 변화율
        - 보유 포지션 평균 미실현 손익 (있을 경우)

        를 묶어 한 줄 문자열로 반환.
        """
        if not since_ts:
            return "성과: 미평가"

        try:
            trade_row = self._db.execute(
                "SELECT COUNT(*) as cnt FROM trades WHERE side='sell' AND timestamp >= ?",
                (since_ts,),
            ).fetchone()
            trade_cnt = dict(trade_row)["cnt"] or 0
        except Exception:
            trade_cnt = 0

        parts = [f"매매 {trade_cnt}건"]

        # BTC 변화 (분석 시점 스냅샷 대비 현재)
        try:
            btc_prev = self._db.execute(
                """SELECT price FROM market_snapshots
                   WHERE coin='KRW-BTC' AND timestamp <= ?
                   ORDER BY id DESC LIMIT 1""",
                (since_ts,),
            ).fetchone()
            btc_now = self._db.execute(
                "SELECT price FROM market_snapshots WHERE coin='KRW-BTC' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if btc_prev and btc_now:
                p_prev = dict(btc_prev)["price"]
                p_now = dict(btc_now)["price"]
                if p_prev and p_prev > 0 and p_prev != p_now:
                    parts.append(f"BTC {(p_now - p_prev) / p_prev * 100:+.1f}%")
        except Exception as e:
            logger.debug("BTC 변화 조회 실패: %s", e)

        # 보유 포지션 평균 미실현
        try:
            held = self._db.execute(
                """SELECT coin, price FROM trades t WHERE side='buy'
                AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side='sell')"""
            ).fetchall()
            if held:
                import pyupbit

                pcts = []
                for h in held:
                    h = dict(h)
                    cp = pyupbit.get_current_price(h["coin"])
                    if cp and h["price"] > 0:
                        pcts.append((cp - h["price"]) / h["price"] * 100)
                if pcts:
                    parts.append(f"보유 평균 {sum(pcts) / len(pcts):+.1f}%")
        except Exception as e:
            logger.debug("보유 미실현 조회 실패: %s", e)

        return "성과(대체): " + ", ".join(parts)

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
            avg_pnl = r["avg_pnl"] or 0
            lines.append(
                f"  {r['strategy']}: {r['sell_cnt']}건 매도, 승률 {win_rate:.0f}%, 평균 손익 {avg_pnl:+,.0f}원"
            )

        total_trades = sum(dict(r)["sell_cnt"] for r in stats_rows)
        reliability = (
            "적극 참고" if total_trades >= 50 else "참고만 (데이터 부족)" if total_trades >= 10 else "매우 제한적"
        )
        lines.insert(0, f"총 {total_trades}건 매도 — 신뢰도: {reliability}")

        return "\n".join(lines)

    # 코인당 백테스트 결과 표시 수 제한 (토큰 절약)
    TOP_N_PER_COIN = 5

    def _get_backtest_text(self) -> tuple[str, str]:
        """최근 2회 백테스트 결과를 텍스트로 반환.

        스윕으로 레코드가 많으므로 코인당 수익률 Top N만 포함.
        거래 0건이거나 수익률 0%인 의미 없는 결과는 제외.
        파라미터 정보를 함께 표시하여 LLM이 어떤 설정의 결과인지 파악 가능.

        Returns:
            (결과 텍스트, 실행일자) 튜플
        """
        try:
            # 최근 2회 실행일 조회
            date_rows = self._db.execute(
                "SELECT DISTINCT run_date FROM backtest_results ORDER BY run_date DESC LIMIT 2"
            ).fetchall()
            if not date_rows:
                return "백테스트 데이터 없음", "없음"

            run_dates = [dict(d)["run_date"] for d in date_rows]
            placeholders = ",".join("?" * len(run_dates))

            # 거래 0건이거나 수익률 0%인 결과는 LLM 판단에 도움 안 됨 → 쿼리에서 제외
            rows = self._db.execute(
                f"""SELECT coin, strategy_name, total_return_pct, num_trades,
                          win_rate, max_drawdown_pct, sharpe_ratio, period,
                          params_json, run_date
                FROM backtest_results
                WHERE run_date IN ({placeholders})
                  AND num_trades > 0
                  AND total_return_pct != 0
                ORDER BY run_date DESC, coin, total_return_pct DESC""",
                run_dates,
            ).fetchall()

            if not rows:
                return "백테스트 데이터 없음", "없음"

            # 실행일별 → 코인별 그룹핑
            date_groups: dict[str, dict[str, list]] = {}
            for r in rows:
                r = dict(r)
                rd = r["run_date"]
                date_groups.setdefault(rd, {}).setdefault(r["coin"], []).append(r)

            lines = []
            for i, rd in enumerate(run_dates):
                label = "최근 실행" if i == 0 else "이전 실행"
                lines.append(f"### {label}: {rd}")

                coin_groups = date_groups.get(rd, {})
                for coin, results in coin_groups.items():
                    # 코인당 수익률 Top N만
                    top_results = results[: self.TOP_N_PER_COIN]
                    if not top_results:
                        continue
                    period = top_results[0]["period"]
                    lines.append(f"[{coin}] ({period})")
                    for r in top_results:
                        param_str = self._format_backtest_params(r.get("params_json"), r["strategy_name"])
                        entry = f"  {r['strategy_name']}{param_str}: {r['total_return_pct']:+.1f}%"
                        entry += f" | {r['num_trades']}건 승률{r['win_rate']:.0f}%"
                        entry += f" | MDD {r['max_drawdown_pct']:.1f}%"
                        if r["sharpe_ratio"] != 0:
                            entry += f" | sharpe {r['sharpe_ratio']:.2f}"
                        lines.append(entry)
                lines.append("")

            return "\n".join(lines), run_dates[0]
        except Exception as e:
            logger.debug("백테스트 데이터 조회 실패: %s", e)
            return "백테스트 데이터 없음", "없음"

    @staticmethod
    def _format_backtest_params(params_json: str | None, strategy_name: str) -> str:
        """params_json에서 핵심 파라미터(공통 제외)만 간결하게 표시.

        Args:
            params_json: JSON 문자열 또는 None
            strategy_name: 전략 이름

        Returns:
            "(k=0.7)" 형태 문자열. 파라미터가 없으면 빈 문자열.
        """
        if not params_json:
            return ""
        try:
            params = json.loads(params_json) if isinstance(params_json, str) else params_json
        except (json.JSONDecodeError, TypeError):
            return ""

        # 공통 파라미터 제외, 전략 고유 파라미터만
        short_names = {
            "k_value": "k",
            "short_period": "short",
            "long_period": "long",
            "st_multiplier": "st_m",
            "rsi_oversold": "rsi_os",
            "bb_std": "bb",
            "grid_count": "grid",
            "entry_period": "entry",
            "exit_period": "exit",
            "oversold": "os",
            "overbought": "ob",
            "fast": "fast",
            "slow": "slow",
            "bb_period": "bb_p",
            "rsi_period": "rsi_p",
            "st_period": "st_p",
            "signal_period": "sig",
            "squeeze_lookback": "sq_lb",
            "range_pct": "range",
        }
        parts = []
        for key, value in params.items():
            if key in COMMON_PARAM_KEYS:
                continue
            short = short_names.get(key, key)
            if isinstance(value, float) and value == int(value):
                parts.append(f"{short}={int(value)}")
            else:
                parts.append(f"{short}={value}")
        return f"({','.join(parts)})" if parts else ""

    def _get_news_text(self) -> str:
        """최신 뉴스 20개 (항상 포함)."""
        rows = self._db.execute(
            """
            SELECT title, summary, sentiment_keyword, coins_mentioned, source, published_at
            FROM news_articles
            ORDER BY id DESC
            LIMIT 20
            """
        ).fetchall()

        if not rows:
            return "뉴스 데이터 없음"

        lines = []
        for i, r in enumerate(rows, 1):
            r = dict(r)
            coins = f" [{r['coins_mentioned']}]" if r["coins_mentioned"] else ""
            lines.append(f"{i}. [{r['source']}] {r['title']}{coins} ({r['sentiment_keyword']})")
            if r["summary"]:
                lines.append(f"   {r['summary'][:150]}")
        return "\n".join(lines)

    def _get_fear_greed_text(self) -> str:
        """Fear & Greed 최근 4건 (추세 파악용)."""
        rows = self._db.execute(
            "SELECT value, classification, timestamp FROM fear_greed_index ORDER BY id DESC LIMIT 4"
        ).fetchall()
        if not rows:
            return "데이터 없음"
        lines = []
        for i, row in enumerate(rows):
            r = dict(row)
            label = "현재" if i == 0 else f"{i}회 전"
            lines.append(f"{label}: {r['value']} ({r['classification']}) — {r['timestamp']}")
        return "\n".join(lines)

    def _get_market_text(self) -> str:
        """현재 시장 데이터 + RSI 추이 + 가격 변화."""
        rows = self._db.execute(
            """
            SELECT coin, price, rsi_14, ma_5, ma_20, market_state
            FROM market_snapshots
            WHERE id IN (SELECT MAX(id) FROM market_snapshots WHERE coin LIKE 'KRW-%' GROUP BY coin)
            """
        ).fetchall()

        # 1시간 전 데이터 (RSI/가격 추이용)
        # 윈도 제한: -120min ~ -30min 사이 스냅샷만 사용.
        # 제한 없으면 수집 간격이 짧을 때 "바로 직전 스냅샷"이 매칭되어
        # 모든 코인이 +0.0%/1h로 찍히는 버그 발생.
        prev_rows = self._db.execute(
            """
            SELECT coin, price, rsi_14
            FROM market_snapshots
            WHERE timestamp BETWEEN datetime('now', '-120 minutes') AND datetime('now', '-30 minutes')
            AND id IN (
                SELECT MAX(id) FROM market_snapshots
                WHERE timestamp BETWEEN datetime('now', '-120 minutes') AND datetime('now', '-30 minutes')
                GROUP BY coin
            )
            """
        ).fetchall()
        prev_data = {dict(r)["coin"]: dict(r) for r in prev_rows}

        # 거래량 데이터 (ohlcv_daily 최근 2일)
        vol_rows = self._db.execute(
            """
            SELECT coin, volume, date FROM ohlcv_daily
            WHERE date >= DATE('now', '-2 days')
            ORDER BY date DESC
            """
        ).fetchall()
        vol_data: dict = {}
        for v in vol_rows:
            v = dict(v)
            coin = v["coin"]
            if coin not in vol_data:
                vol_data[coin] = {"today": v["volume"]}
            elif "prev" not in vol_data[coin]:
                vol_data[coin]["prev"] = v["volume"]

        lines = []
        for r in rows:
            r = dict(r)
            name = r["coin"].replace("KRW-", "")
            rsi = r["rsi_14"]
            state = r["market_state"] or "?"

            # RSI 추이
            rsi_str = f"RSI={rsi:.0f}" if rsi else ""
            prev = prev_data.get(r["coin"])
            if prev and rsi and prev.get("rsi_14"):
                rsi_diff = rsi - prev["rsi_14"]
                arrow = "↑" if rsi_diff > 2 else "↓" if rsi_diff < -2 else "→"
                rsi_str = f"RSI={rsi:.0f}{arrow}"

            # 가격 변화 — prev가 있고 실제로 가격이 다를 때만 표기
            # (prev == now는 같은 스냅샷을 재참조한 케이스로 의미 없음)
            price_str = f"{r['price']:,.0f}원"
            if prev and prev.get("price") and prev["price"] > 0 and prev["price"] != r["price"]:
                pct = (r["price"] - prev["price"]) / prev["price"] * 100
                price_str += f" ({pct:+.1f}%/1h)"

            # 거래량 변화
            vol_str = ""
            vd = vol_data.get(r["coin"])
            if vd and vd.get("today") and vd.get("prev") and vd["prev"] > 0:
                vol_chg = (vd["today"] - vd["prev"]) / vd["prev"] * 100
                vol_str = f" | 거래량 {vol_chg:+.0f}%"

            lines.append(f"{name}: {price_str} | {state} | {rsi_str}{vol_str}")
        return "\n".join(lines) if lines else "시장 데이터 없음"

    def _get_performance_text(self) -> str:
        """최근 매매 성과 + 손익비 + 매매 상세 + 보유 포지션."""
        lines = []

        # 1. 24시간 요약
        row = self._db.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                SUM(profit_krw) as total_pnl,
                AVG(CASE WHEN profit_pct > 0 THEN profit_pct END) as avg_win_pct,
                AVG(CASE WHEN profit_pct <= 0 THEN profit_pct END) as avg_loss_pct
            FROM trades WHERE side = 'sell'
            AND trigger_reason NOT LIKE '[BUG]%'
            AND timestamp >= datetime('now', '-24 hours')
            """
        ).fetchone()
        r = dict(row)
        total = r["total"] or 0
        if total > 0:
            win_rate = (r["wins"] or 0) / total * 100
            avg_win = r["avg_win_pct"] or 0
            avg_loss = abs(r["avg_loss_pct"] or 0)
            lines.append(f"[24시간] {total}건, 승률 {win_rate:.0f}%, 손익 {r['total_pnl'] or 0:+,.0f}원")
            if avg_win > 0 and avg_loss > 0:
                # 손익비 = 평균승 / 평균패 (높을수록 이길 때 더 크게 이김). 목표 1.5 이상.
                reward_risk = avg_win / avg_loss
                lines.append(
                    f"  평균 승: +{avg_win:.2f}%, 평균 패: -{avg_loss:.2f}%, 손익비 {reward_risk:.2f} (목표 ≥ 1.5)"
                )
                if reward_risk < 1.0:
                    lines.append("  ⚠️ 손익비 1.0 미만 — 한 번 질 때 이익을 모두 날림. ROI 상향 필요.")
            elif avg_win > 0:
                lines.append(f"  평균 승: +{avg_win:.2f}% (손실 건 없음)")
            elif avg_loss > 0:
                lines.append(f"  평균 패: -{avg_loss:.2f}% (승 건 없음)")
        else:
            lines.append("[24시간] 매매 없음")

        # 2. 최근 매매 상세 (최신 8건)
        trades = self._db.execute(
            """
            SELECT coin, strategy, ROUND(profit_pct, 2) as pct, trigger_reason,
                hold_duration_minutes as hold
            FROM trades WHERE side='sell' AND trigger_reason NOT LIKE '[BUG]%'
            ORDER BY id DESC LIMIT 8
            """
        ).fetchall()
        if trades:
            lines.append("\n[최근 매매]")
            for t in trades:
                t = dict(t)
                coin = t["coin"].replace("KRW-", "")
                lines.append(f"  {coin} {t['pct']:+.2f}% ({t['hold'] or 0}분) — {t['trigger_reason'][:40]}")

        # 3. 전략별 24시간 성과
        strats = self._db.execute(
            """
            SELECT strategy, COUNT(*) as cnt,
                ROUND(AVG(profit_pct), 2) as avg_pct,
                SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins
            FROM trades WHERE side='sell' AND timestamp >= datetime('now', '-24 hours')
            AND trigger_reason NOT LIKE '[BUG]%'
            GROUP BY strategy
            """
        ).fetchall()
        if strats:
            lines.append("\n[전략별 24시간]")
            for s in strats:
                s = dict(s)
                wr = round((s["wins"] or 0) / s["cnt"] * 100) if s["cnt"] > 0 else 0
                lines.append(f"  {s['strategy']}: {s['cnt']}건, 승률 {wr}%, 평균 {s['avg_pct']:+.2f}%")

        # 4. 현재 보유 포지션 손익
        held = self._db.execute(
            """
            SELECT coin, price, total_krw FROM trades t
            WHERE side='buy'
            AND NOT EXISTS (SELECT 1 FROM trades s WHERE s.buy_trade_id = t.id AND s.side='sell')
            """
        ).fetchall()
        if held:
            lines.append("\n[보유 포지션]")
            try:
                import pyupbit

                for h in held:
                    h = dict(h)
                    coin = h["coin"]
                    cp = pyupbit.get_current_price(coin)
                    if cp and h["price"] > 0:
                        pnl = (cp - h["price"]) / h["price"] * 100
                        sym = coin.replace("KRW-", "")
                        lines.append(f"  {sym}: 매수 {h['price']:,.0f} → 현재 {cp:,.0f} ({pnl:+.1f}%)")
            except Exception:
                lines.append("  (가격 조회 실패)")

        return "\n".join(lines)

    def _get_current_strategy_params(self) -> str:
        """현재 봇에 적용 중인 전략 파라미터."""
        lines = []

        # bot_config 값
        for key in ["stop_loss_pct", "trailing_stop_pct", "k_value", "max_position_per_coin_pct"]:
            row = self._db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
            if row:
                lines.append(f"  {key}: {dict(row)['value']}")

        # 전략별 파라미터
        rows = self._db.execute(
            "SELECT name, default_params_json FROM strategies WHERE name IN ('bb_rsi_combined', 'volatility_breakout')"
        ).fetchall()
        for r in rows:
            r = dict(r)
            lines.append(f"  {r['name']}: {r['default_params_json']}")

        return "\n".join(lines) if lines else "설정 없음"

    def _get_strategies_text(self) -> str:
        """DB에서 사용 가능한 전략 목록을 동적으로 생성."""
        try:
            rows = self._db.execute(
                """SELECT name, display_name, description, category, market_states, default_params_json
                FROM strategies WHERE is_available = TRUE
                ORDER BY name"""
            ).fetchall()

            if not rows:
                return "사용 가능한 전략 없음"

            lines = []
            for r in rows:
                r = dict(r)
                name = r["name"]
                display = r["display_name"] or name
                category = r["category"] or "기타"
                markets = r["market_states"] or "all"
                desc = r["description"] or ""

                line = f"### {name} ({display}) [{category}]"
                lines.append(line)
                if desc:
                    lines.append(f"- 설명: {desc}")
                lines.append(f"- 적합 시장: {markets}")

                # 조절 가능한 파라미터 목록 + 하드 리밋 범위
                if r["default_params_json"]:
                    try:
                        params = json.loads(r["default_params_json"])
                        param_parts = []
                        for k, v in params.items():
                            limit = HARD_LIMITS.get(k)
                            if limit:
                                param_parts.append(f"{k}={v} ({limit[0]}~{limit[1]})")
                            else:
                                param_parts.append(f"{k}={v}")
                        if param_parts:
                            lines.append(f"- 조절 파라미터: {', '.join(param_parts)}")
                    except (json.JSONDecodeError, TypeError):
                        pass
                lines.append("")  # 빈 줄로 구분

            return "\n".join(lines)
        except Exception as e:
            logger.debug("전략 목록 조회 실패: %s", e)
            return "전략 목록 조회 실패"

    def _get_active_strategy_text(self) -> str:
        """현재 활성 전략 정보를 텍스트로 생성."""
        try:
            row = self._db.execute(
                """SELECT name, display_name, description, market_states, default_params_json
                FROM strategies WHERE is_active = TRUE LIMIT 1"""
            ).fetchone()

            if not row:
                return "활성 전략 없음 (기본 전략 사용 중)"

            r = dict(row)
            lines = [
                f"전략: {r['name']} ({r['display_name'] or r['name']})",
                f"적합 시장: {r['market_states'] or 'all'}",
            ]

            if r["default_params_json"]:
                try:
                    params = json.loads(r["default_params_json"])
                    param_str = ", ".join(f"{k}={v}" for k, v in params.items())
                    lines.append(f"파라미터: {param_str}")
                except (json.JSONDecodeError, TypeError):
                    pass

            # 최근 성과 요약 (활성 전략 기준)
            perf = self._db.execute(
                """SELECT COUNT(*) as cnt,
                    SUM(CASE WHEN profit_krw > 0 THEN 1 ELSE 0 END) as wins,
                    AVG(profit_pct) as avg_pct
                FROM trades WHERE side='sell' AND strategy = ?
                AND timestamp >= datetime('now', '-7 days')""",
                (r["name"],),
            ).fetchone()
            if perf:
                p = dict(perf)
                cnt = p["cnt"] or 0
                if cnt > 0:
                    wr = round((p["wins"] or 0) / cnt * 100)
                    lines.append(f"최근 7일 성과: {cnt}건 매도, 승률 {wr}%, 평균 {p['avg_pct'] or 0:+.2f}%")
                else:
                    lines.append("최근 7일 성과: 매매 없음")

            return "\n".join(lines)
        except Exception as e:
            logger.debug("활성 전략 조회 실패: %s", e)
            return "활성 전략 조회 실패"

    # 필수 응답 필드
    REQUIRED_FIELDS = ["market_summary_kr", "market_state", "recommended_strategy"]
    REQUIRED_PARAMS = [
        "rsi_oversold",
        "bb_std",
        "stop_loss_pct",
        "trailing_stop_pct",
        "k_value",
        "max_position_per_coin_pct",
        "roi_60min",
        "roi_120min",
    ]
    MAX_RETRIES = 2

    def _call_claude(self, prompt: str) -> dict | None:
        """Claude API 호출 (최대 2회 재시도 + 응답 검증)."""
        import time as _time

        import anthropic

        total_input = 0
        total_output = 0

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                client = anthropic.Anthropic(api_key=self._api_key)
                response = client.messages.create(
                    model=self._model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                )

                total_input += response.usage.input_tokens
                total_output += response.usage.output_tokens

                content = response.content[0].text.strip()

                # JSON 파싱
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()

                result = json.loads(content)

                # 필수 필드 검증
                missing = [f for f in self.REQUIRED_FIELDS if f not in result]
                if missing:
                    logger.warning("LLM 응답 필수 필드 누락 (시도 %d/%d): %s", attempt, self.MAX_RETRIES, missing)
                    if attempt < self.MAX_RETRIES:
                        _time.sleep(2)
                        continue
                    # 마지막 시도 — 누락 필드에 기본값 채우기
                    result = self._fill_defaults(result)

                # 파라미터 누락 시 과거 값으로 채우기
                result["recommended_params"] = self._fill_param_defaults(result.get("recommended_params", {}))

                result["_input_tokens"] = total_input
                result["_output_tokens"] = total_output
                result["_model"] = self._model

                logger.info(
                    "Claude 응답 (시도 %d): %d input + %d output 토큰",
                    attempt,
                    total_input,
                    total_output,
                )
                return result

            except json.JSONDecodeError as e:
                logger.warning("LLM JSON 파싱 실패 (시도 %d/%d): %s", attempt, self.MAX_RETRIES, e)
                if attempt < self.MAX_RETRIES:
                    _time.sleep(2)
                    continue

            except Exception as e:
                logger.error("Claude API 호출 실패 (시도 %d/%d): %s", attempt, self.MAX_RETRIES, e)
                if attempt < self.MAX_RETRIES:
                    _time.sleep(3)
                    continue

        logger.error("LLM 분석 최종 실패 (%d회 시도) — 과거 데이터 유지", self.MAX_RETRIES)
        return None

    def _fill_defaults(self, result: dict) -> dict:
        """필수 필드 누락 시 기본값 채우기."""
        defaults = {
            "market_summary_kr": "LLM 응답 불완전 — 기존 설정 유지",
            "market_state": "sideways",
            "confidence": 0.5,
            "aggression": 0.3,
            "should_alert_stop": False,
            "recommended_strategy": "bb_rsi_combined",
            "reasoning": "LLM 응답 불완전으로 보수적 기본값 적용",
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default
                logger.warning("기본값 적용: %s = %s", key, default)
        return result

    def _fill_param_defaults(self, params: dict) -> dict:
        """파라미터 누락 시 현재 bot_config + 전략 파라미터에서 가져와 채우기."""
        # bot_config 기반
        config_keys = {
            "stop_loss_pct": "stop_loss_pct",
            "trailing_stop_pct": "trailing_stop_pct",
            "k_value": "k_value",
            "max_position_per_coin_pct": "max_position_per_coin_pct",
        }
        for param_key, config_key in config_keys.items():
            if param_key not in params:
                row = self._db.execute("SELECT value FROM bot_config WHERE key = ?", (config_key,)).fetchone()
                if row:
                    try:
                        params[param_key] = float(dict(row)["value"])
                    except (ValueError, TypeError):
                        pass

        # 전략 파라미터 기반 (rsi_oversold, bb_std 등) — 활성 전략에서 읽기
        strategy_keys = ["rsi_oversold", "bb_std"]
        for key in strategy_keys:
            if key not in params:
                row = self._db.execute(
                    "SELECT default_params_json FROM strategies WHERE is_active = TRUE LIMIT 1"
                ).fetchone()
                if row and dict(row)["default_params_json"]:
                    try:
                        sp = json.loads(dict(row)["default_params_json"])
                        if key in sp:
                            params[key] = sp[key]
                    except (json.JSONDecodeError, TypeError):
                        pass
        return params

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
        prev = self._db.execute("SELECT id, timestamp FROM llm_decisions ORDER BY id DESC LIMIT 1").fetchone()
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
            logger.info(
                "이전 LLM 성과: %d건 매매, PnL %+,.0f원, 판단 %s", r["trades"], pnl, "good" if was_good else "bad"
            )

    def _apply_recommendations(self, result: dict) -> None:
        """LLM 권고를 bot_config에 반영. before/after 스냅샷 기록."""
        params = result.get("recommended_params", {})
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 이전 성과 평가
        self._evaluate_previous()

        # before 스냅샷 (bot_config + 전략 파라미터)
        before = {}
        config_keys = [
            "stop_loss_pct",
            "trailing_stop_pct",
            "k_value",
            "allow_trading",
            "max_position_per_coin_pct",
        ]
        for key in config_keys:
            row = self._db.execute("SELECT value FROM bot_config WHERE key = ?", (key,)).fetchone()
            if row:
                before[key] = dict(row)["value"]
        # 전략 파라미터도 before에 포함 (활성 전략의 모든 파라미터)
        active_row = self._db.execute(
            "SELECT name, default_params_json FROM strategies WHERE is_active = TRUE LIMIT 1"
        ).fetchone()
        if active_row and dict(active_row)["default_params_json"]:
            try:
                sp = json.loads(dict(active_row)["default_params_json"])
                for k, v in sp.items():
                    before[f"strategy:{k}"] = v
                before["active_strategy"] = dict(active_row)["name"]
            except (json.JSONDecodeError, TypeError):
                pass

        # 파라미터 적용
        config_map = {
            "stop_loss_pct": params.get("stop_loss_pct"),
            "trailing_stop_pct": params.get("trailing_stop_pct"),
            "k_value": params.get("k_value"),
            "max_position_per_coin_pct": params.get("max_position_per_coin_pct"),
            "max_spread_pct": params.get("max_spread_pct"),
            "emergency_held_pct": params.get("emergency_held_pct"),
            "emergency_non_held_pct": params.get("emergency_non_held_pct"),
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

        # 전략 활성화 + 파라미터 반영
        strategy = result.get("recommended_strategy")
        if strategy:
            # 전략 전환 (is_active 업데이트)
            from cryptobot.data.strategy_repository import StrategyRepository

            repo = StrategyRepository(self._db)
            activated = repo.activate(strategy, source="llm", reason="LLM 분석에서 추천")
            if not activated:
                logger.warning("전략 활성화 실패: %s — 기존 전략 유지", strategy)

            # 기존 파라미터 로드
            row = self._db.execute("SELECT default_params_json FROM strategies WHERE name = ?", (strategy,)).fetchone()
            strategy_params = (
                json.loads(dict(row)["default_params_json"]) if row and dict(row)["default_params_json"] else {}
            )

            # LLM 추천값으로 머지 — 공통 키 제외한 전략별 파라미터 모두 반영
            for key, value in params.items():
                if key not in COMMON_PARAM_KEYS:
                    strategy_params[key] = value

            self._db.execute(
                "UPDATE strategies SET default_params_json = ?, updated_at = ? WHERE name = ?",
                (json.dumps(strategy_params), now, strategy),
            )

        # ROI 테이블 반영 (기본값에 덮어쓰기)
        roi_keys = {"roi_10min": 10, "roi_30min": 30, "roi_60min": 60, "roi_120min": 120}
        roi_changed = any(key in params for key in roi_keys)
        if roi_changed:
            roi_table = {10: 3.0, 30: 2.0, 60: 1.0, 120: 0.1}  # 기본값
            # 기존 DB 값 로드
            existing = self._db.execute("SELECT value FROM bot_config WHERE key = 'roi_table'").fetchone()
            if existing and dict(existing)["value"]:
                try:
                    roi_table.update({int(k): float(v) for k, v in json.loads(dict(existing)["value"]).items()})
                except (json.JSONDecodeError, ValueError):
                    pass
            # LLM 추천값 머지
            for key, minutes in roi_keys.items():
                if key in params:
                    roi_table[minutes] = params[key]
            self._db.execute(
                "INSERT OR REPLACE INTO bot_config "
                "(key, value, value_type, category, display_name, description, updated_at) "
                "VALUES ('roi_table', ?, 'string', 'strategy', 'ROI 테이블', "
                "'LLM 조절 시간별 목표 수익률', ?)",
                (json.dumps(roi_table), now),
            )
            logger.info("ROI 테이블 갱신: %s", roi_table)

        # 코인 추천 반영
        coin_recs = result.get("coin_recommendations", {})
        add_coins = coin_recs.get("add", [])
        remove_coins = coin_recs.get("remove", [])
        if add_coins or remove_coins:
            # KRW- 접두사 보장
            add_coins = [c if c.startswith("KRW-") else f"KRW-{c}" for c in add_coins]
            remove_coins = [c if c.startswith("KRW-") else f"KRW-{c}" for c in remove_coins]

            self._db.execute(
                "UPDATE bot_config SET value = ?, updated_at = ? WHERE key = 'llm_add_coins'",
                (json.dumps(add_coins), now),
            )
            self._db.execute(
                "UPDATE bot_config SET value = ?, updated_at = ? WHERE key = 'llm_remove_coins'",
                (json.dumps(remove_coins), now),
            )
            reasons = coin_recs.get("reasons", "")
            logger.info("LLM 코인 추천: add=%s, remove=%s (%s)", add_coins, remove_coins, reasons)

        # after 스냅샷 (전략 파라미터 포함)
        after = {k: str(v) for k, v in config_map.items() if v is not None}
        if result.get("allow_trading") is not None:
            after["allow_trading"] = str(result["allow_trading"]).lower()
        if strategy:
            after["active_strategy"] = strategy
        for key, value in params.items():
            if key not in COMMON_PARAM_KEYS:
                after[f"strategy:{key}"] = value

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
