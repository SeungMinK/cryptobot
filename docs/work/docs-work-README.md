# Development Work Hub

> 이 폴더는 개발 작업 문서를 관리합니다.
> 각 문서는 독립적으로 참조 가능하며, Claude에 붙여넣어 바이브코딩 컨텍스트로 활용합니다.

## 문서 구조

```
docs/work/
├── README.md                ← 지금 이 파일 (메인 허브)
├── 01-setup.md              (예정) 개발 환경 설정 상세
├── 02-database-schema.md    (예정) DB 스키마 + 마이그레이션
├── 03-strategy-guide.md     (예정) 매매 전략 상세 + 백테스트 결과
├── 04-llm-integration.md    (예정) LLM 연동 설계 + 프롬프트
├── 05-dashboard.md          (예정) 대시보드 기능 명세
├── 06-infra.md              (예정) Docker + Cloud 배포 가이드
└── 07-retrospective.md      (예정) 주간/월간 회고 + 성과 기록
```

---

## 개발 로드맵

### Phase 1: MVP — 자동매매 기본 동작
**목표**: 봇이 BTC를 변동성 돌파 전략으로 자동 매수/매도하고, Slack으로 알림을 보내는 것
**기간**: 첫 날 ~ 1주

| Issue | 제목 | 예상 시간 | 상태 |
|-------|------|----------|------|
| #1 | 개발 환경 설정 | 15분 | ⬜ |
| #2 | API Key 발급 + 연결 테스트 | 15분 | ⬜ |
| #3 | 설정 관리 모듈 (config.py) | 10분 | ⬜ |
| #4 | 데이터베이스 초기화 | 15분 | ⬜ |
| #5 | 기술적 지표 계산 모듈 | 20분 | ⬜ |
| #6 | 변동성 돌파 전략 엔진 | 30분 | ⬜ |
| #7 | 주문 실행 모듈 | 20분 | ⬜ |
| #8 | 시장 데이터 수집기 | 15분 | ⬜ |
| #9 | Slack 알림 모듈 | 15분 | ⬜ |
| #10 | 메인 루프 + 스케줄러 | 20분 | ⬜ |

### Phase 2: 고도화 — LLM + 분석
**목표**: Claude Haiku가 시장 상황을 분석하여 파라미터를 자동 조절하고, 대시보드에서 성과를 확인
**기간**: 1~3개월

| Issue | 제목 | 상태 |
|-------|------|------|
| #11 | Streamlit 대시보드 — 전체 현황 | ⬜ |
| #12 | Streamlit 대시보드 — 거래내역 | ⬜ |
| #13 | Streamlit 대시보드 — 수익률 분석 | ⬜ |
| #14 | 뉴스 수집기 (RSS) | ⬜ |
| #15 | Claude Haiku 연동 — 시장분석 | ⬜ |
| #16 | LLM 파라미터 튜닝 — 매매 결과 피드백 | ⬜ |
| #17 | 백테스트 엔진 | ⬜ |

### Phase 3: 인프라 — 컨테이너화
**기간**: 3~4개월

| Issue | 제목 | 상태 |
|-------|------|------|
| #18 | Docker 컨테이너화 | ⬜ |
| #19 | SQLite → PostgreSQL 마이그레이션 | ⬜ |

### Phase 4: 클라우드 — 배포 + 오케스트레이션
**기간**: 6개월

| Issue | 제목 | 상태 |
|-------|------|------|
| #20 | Airflow DAG 설계 | ⬜ |
| #21 | 클라우드 배포 (Oracle/AWS) | ⬜ |

---

## 데이터 설계

### 설계 원칙: "모든 판단의 근거와 결과를 함께 저장한다"

이 프로젝트의 데이터 설계가 일반 트레이딩 봇과 다른 점은,
매매 결과뿐 아니라 **그 판단을 내린 시점의 모든 컨텍스트**를 저장한다는 것입니다.
이렇게 해야 나중에 LLM이 "어떤 상황에서 어떤 파라미터가 잘 먹혔는지" 학습할 수 있습니다.

### 데이터 흐름

```
[수집]                    [판단]                  [실행]               [평가]
                                                  
시장 데이터 ──→ 기술적 지표 ──→ 매매 신호 ──→ 주문 체결 ──→ 손익 계산
(1분마다)       (RSI, MA 등)    (buy/sell)     (trades)     (daily_reports)
    │                              │                │              │
    ▼                              ▼                ▼              ▼
market_snapshots           trade_signals         trades      daily_reports
                                                    │
                                                    ▼
                           [LLM 피드백 루프]    strategy_params
                                                    │
                           뉴스 + 시장 + 성과 ──→ LLM 판단 ──→ 파라미터 갱신
                                                    │
                                                    ▼
                                              llm_decisions
```

### 테이블 요약

#### market_snapshots — 시장 상태 시계열
1분마다 수집. BTC 가격, 거래량, 기술적 지표(RSI, MA, BB, ATR), 시장 상태 판단.
**용도**: 매매 시점의 시장 상태 복원, 백테스트, LLM 입력

```sql
CREATE TABLE market_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    btc_price REAL NOT NULL,
    btc_open_24h REAL,
    btc_high_24h REAL,
    btc_low_24h REAL,
    btc_change_pct_24h REAL,
    btc_volume_24h REAL,
    btc_trade_count_24h INTEGER,
    btc_rsi_14 REAL,
    btc_ma_5 REAL,
    btc_ma_20 REAL,
    btc_ma_60 REAL,
    btc_bb_upper REAL,
    btc_bb_lower REAL,
    btc_atr_14 REAL,
    total_market_volume_krw REAL,
    top10_avg_change_pct REAL,
    market_state TEXT,            -- 'bullish' / 'bearish' / 'sideways'
    volatility_level TEXT,        -- 'low' / 'medium' / 'high'
    UNIQUE(timestamp)
);
```

#### trade_signals — 매매 신호 (실행 안 된 것도 기록)
**왜 중요한가**: "이 신호를 무시했는데 실제로는 수익이었을까?" 사후 분석 가능.
skip_reason에 미실행 사유를 저장하여 전략 개선에 활용.

```sql
CREATE TABLE trade_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    coin TEXT NOT NULL,
    signal_type TEXT NOT NULL,       -- 'buy_signal' / 'sell_signal' / 'hold'
    strategy TEXT NOT NULL,
    confidence REAL,                 -- 0.0 ~ 1.0
    trigger_reason TEXT,
    trigger_value REAL,
    current_price REAL,
    target_price REAL,
    executed BOOLEAN DEFAULT FALSE,
    trade_id INTEGER,
    skip_reason TEXT,                -- 'insufficient_balance', 'market_bearish', 'max_positions'
    snapshot_id INTEGER,
    FOREIGN KEY (trade_id) REFERENCES trades(id),
    FOREIGN KEY (snapshot_id) REFERENCES market_snapshots(id)
);
```

#### trades — 매매 체결 기록
**핵심**: 매매 시점의 파라미터 + 시장 상태를 함께 저장.
매도 시 대응 매수 trade를 buy_trade_id로 연결하여 페어 분석 가능.

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    coin TEXT NOT NULL,
    side TEXT NOT NULL,              -- 'buy' / 'sell'
    price REAL NOT NULL,
    amount REAL NOT NULL,
    total_krw REAL NOT NULL,
    fee_krw REAL NOT NULL,
    strategy TEXT NOT NULL,
    trigger_reason TEXT,
    trigger_value REAL,
    param_k_value REAL,              -- 이 매매에 적용된 K값
    param_stop_loss REAL,
    param_trailing_stop REAL,
    market_state_at_trade TEXT,
    btc_price_at_trade REAL,
    rsi_at_trade REAL,
    buy_trade_id INTEGER,            -- 매도 시: 대응 매수 ID
    profit_pct REAL,                 -- 매도 시 수익률
    profit_krw REAL,                 -- 매도 시 수익금
    hold_duration_minutes INTEGER,   -- 매도 시 보유 시간
    FOREIGN KEY (buy_trade_id) REFERENCES trades(id)
);
```

#### strategy_params — 전략 파라미터 이력
파라미터가 변경될 때마다 기록. source로 누가 변경했는지(수동/LLM/백테스트) 추적.
적용 기간의 성과를 다음 변경 시 소급 계산하여 "어떤 파라미터가 잘 먹혔는지" 분석.

```sql
CREATE TABLE strategy_params (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,            -- 'manual' / 'llm' / 'backtest' / 'default'
    k_value REAL NOT NULL,
    stop_loss_pct REAL NOT NULL,
    trailing_stop_pct REAL NOT NULL,
    max_positions INTEGER NOT NULL,
    position_size_pct REAL,
    allow_trading BOOLEAN NOT NULL DEFAULT TRUE,
    market_state TEXT,
    aggression REAL,                 -- 0.0 ~ 1.0
    llm_reasoning TEXT,
    llm_news_summary TEXT,
    llm_model TEXT,
    period_trade_count INTEGER,      -- 소급 계산
    period_win_rate REAL,
    period_total_pnl_pct REAL
);
```

#### daily_reports — 일일 정산
매일 자정 자동 생성. 수익률, 거래 통계, 리스크 지표.

```sql
CREATE TABLE daily_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL UNIQUE,
    starting_balance_krw REAL,
    ending_balance_krw REAL,
    total_asset_value_krw REAL,
    realized_pnl_krw REAL,
    unrealized_pnl_krw REAL,
    daily_return_pct REAL,
    cumulative_return_pct REAL,
    total_trades INTEGER,
    buy_trades INTEGER,
    sell_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate REAL,
    avg_profit_pct REAL,
    avg_loss_pct REAL,
    max_drawdown_pct REAL,
    total_fees_krw REAL,
    active_param_id INTEGER,
    market_state TEXT,
    FOREIGN KEY (active_param_id) REFERENCES strategy_params(id)
);
```

#### llm_decisions — LLM 판단 기록 (Phase 2)
LLM의 입력/출력/비용/사후 평가를 전부 저장.
evaluation_was_good로 "이 판단이 좋았는지" 추적하여 LLM 피드백 루프 구현.

```sql
CREATE TABLE llm_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    model TEXT NOT NULL,
    input_news_count INTEGER,
    input_news_summary TEXT,
    input_market_snapshot_id INTEGER,
    input_recent_trades_count INTEGER,
    input_recent_win_rate REAL,
    output_raw_json TEXT,
    output_market_state TEXT,
    output_aggression REAL,
    output_allow_trading BOOLEAN,
    output_k_value REAL,
    output_stop_loss REAL,
    output_trailing_stop REAL,
    output_reasoning TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cost_usd REAL,
    evaluation_period_pnl_pct REAL,
    evaluation_was_good BOOLEAN,
    FOREIGN KEY (input_market_snapshot_id) REFERENCES market_snapshots(id)
);
```

---

## LLM 연동 설계 (Phase 2)

### 동작 구조

```
하루 4번 (06:00, 12:00, 18:00, 00:00)

[입력 수집]
├── 최근 6시간 뉴스 (RSS)
├── 현재 market_snapshot
├── 최근 7일 매매 결과 요약
│   ├── 시장 상태별 승률
│   ├── 파라미터별 수익률
│   └── 시간대별 성과
├── 이전 LLM 판단의 사후 평가
└── 현재 strategy_params

        ↓

[Claude Haiku API 호출]

        ↓

[출력 파싱]
{
  "market_state": "bullish",
  "allow_trading": true,
  "k_value": 0.4,
  "stop_loss": -0.03,
  "trailing_stop": -0.02,
  "max_positions": 3,
  "aggression": 0.7,
  "reasoning": "미국 ETF 자금 유입 지속, BTC RSI 55로 중립..."
}

        ↓

[적용]
├── strategy_params 업데이트 (source='llm')
├── llm_decisions에 전체 기록
└── Slack으로 파라미터 변경 알림
```

### 피드백 루프

LLM이 자기 판단의 성과를 학습하는 구조:

```
1. LLM이 파라미터 A를 설정
2. 6시간 동안 파라미터 A로 매매
3. 다음 호출 시: "파라미터 A 적용 기간의 수익률은 +2.3%였음"
4. LLM이 이 결과를 참고하여 파라미터 B를 설정
5. llm_decisions.evaluation_period_pnl_pct에 소급 기록
```

### 매매 결과 요약 생성 (LLM 입력용)

```python
def generate_performance_summary(days=7):
    """최근 N일 매매 결과를 LLM 입력용으로 요약"""
    return {
        "period": f"last_{days}_days",
        "overall": {
            "total_trades": 15,
            "win_rate": 0.65,
            "total_pnl_pct": 3.2,
            "avg_win_pct": 3.1,
            "avg_loss_pct": -2.8,
            "max_drawdown_pct": -4.5
        },
        "by_market_state": {
            "bullish":  {"trades": 8,  "win_rate": 0.80, "pnl_pct": 5.5},
            "sideways": {"trades": 5,  "win_rate": 0.40, "pnl_pct": -1.2},
            "bearish":  {"trades": 2,  "win_rate": 0.00, "pnl_pct": -3.0}
        },
        "by_params": {
            "k=0.5,sl=-5%,ts=-3%": {"trades": 10, "win_rate": 0.70, "pnl_pct": 4.1},
            "k=0.3,sl=-3%,ts=-2%": {"trades": 5,  "win_rate": 0.40, "pnl_pct": -0.9}
        },
        "previous_llm_decision": {
            "params": {"k": 0.5, "stop_loss": -0.03},
            "period_pnl_pct": 1.8,
            "was_good": True
        }
    }
```

### 비용

```
모델: Claude Haiku 4.5
입력: ~3,000 tokens / 호출
출력: ~500 tokens / 호출
1회 비용: ~$0.005
하루 4회: ~$0.02
월간: ~$0.6 (약 800원)
```

---

## 매매 전략 상세

### 1. 변동성 돌파 (Phase 1 핵심)

```
매수:
  현재가 > 당일시가 + (전일고가 - 전일저가) × K

매도 (아래 중 먼저 발동):
  1. 트레일링 스탑: 고점 대비 trailing_stop_pct 하락
  2. 손절: 매수가 대비 stop_loss_pct 하락
```

### 2. 시장 상태 필터

```
BTC 기준 MA(5)와 MA(20) 비교:
  bullish  → 정상 매매 (공격적)
  sideways → 소극적 매매 (포지션 축소)
  bearish  → 매매 중단 (현금 대기)
```

### 3. LLM 파라미터 조절 (Phase 2)

```
시장 상태별 파라미터 가이드:

상승장 (bullish):
  K=0.3~0.5, 손절=-3%, 트레일링=-2%, 종목 3~4개

횡보장 (sideways):
  K=0.6~0.7, 손절=-5%, 트레일링=-4%, 종목 1~2개

하락장 (bearish):
  매매 중단, 전액 현금 대기
```

---

## 운영 가이드

### Mac 2대 운영 구조

```
Mac 1 (개발 + 분석)           Mac 2 (운영, 항상 ON)
├── 코드 작성/수정             ├── 봇 24시간 실행
├── 백테스트                   ├── 실매매
├── 대시보드 분석              └── 데이터 수집
└── git push ──────────→ git pull + 봇 재시작
```

### 백그라운드 실행

```bash
# tmux (권장)
tmux new -s cryptobot
source venv/bin/activate
python bot/main.py
# Ctrl+B → D 로 detach

# 복귀
tmux attach -t cryptobot
```

### 봇 재시작 시 안전 장치

봇이 재시작되면 자동으로:
1. 미체결 주문 전부 취소
2. 현재 보유 종목 확인 → 내부 상태와 동기화
3. 마지막 종료 시점 로깅
4. Slack으로 재시작 알림

---

## 보안 체크리스트

```
□ .env 파일이 .gitignore에 포함되어 있는가
□ 업비트 API Key에 "출금" 권한이 없는가
□ API Key에 IP 제한이 설정되어 있는가
□ git log에 API Key가 노출된 커밋이 없는가
□ Streamlit 대시보드가 외부에 노출되지 않는가
```

---

## 비용 요약

| 항목 | Phase 1 | Phase 2 | Phase 4 |
|------|---------|---------|---------|
| 서버 | 0원 | 0원 | 0~7,000원 |
| Claude API | - | ~800원 | ~800원 |
| 거래 수수료 | ~3,000원 | ~3,000원 | ~3,000원 |
| **합계** | **~3,000원** | **~3,800원** | **~10,800원** |

---

## 참고 자료

- [pyupbit GitHub](https://github.com/sharebook-kr/pyupbit)
- [업비트 Open API](https://docs.upbit.com/)
- [위키독스 — 파이썬 자동매매](https://wikidocs.net/book/1665)
- [Anthropic Claude API](https://docs.anthropic.com/)
- [Streamlit 공식 문서](https://docs.streamlit.io/)
- [APScheduler 문서](https://apscheduler.readthedocs.io/)
