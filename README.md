# CryptoBot

AI 기반 코인 자동매매 시스템. 규칙 기반 매매 전략에 LLM(Claude) 시장분석을 결합하여 매매 파라미터를 자동 조절하는 개인용 트레이딩 봇.

## Overview

업비트 API를 통해 코인을 자동으로 매수/매도하고, 매매 데이터를 축적하여 전략을 지속적으로 개선하는 시스템입니다. 단순한 자동매매를 넘어, 데이터 수집 → 변환 → 분석 → 자동화를 아우르는 데이터 파이프라인으로 설계되었습니다.

### Core Features

- **9개 매매 전략**: 변동성 돌파, 볼린저 밴드, RSI, MACD, 이동평균 교차 등 (Admin에서 전환)
- **신호 강도 기반 포지션 사이징**: confidence에 비례하여 매수 금액 자동 결정
- **실시간 리스크 관리**: 손절/트레일링 스탑/일일 손실 제한/연속 손실 차단
- **데이터 파이프라인**: 10초 간격 시장 데이터 수집, 매매 신호/결과 기록, OHLCV 히스토리 저장
- **React Admin 대시보드**: 대시보드, 매매 내역, 전략 관리, 매매 신호, 수익률 분석, 설정
- **Slack 알림**: 매매 체결/수익/에러/틱별 판단 리포트 (Bot Token 방식)
- **에러 로깅**: 날짜별 에러/경고 파일 저장 (`error/yyyy-mm-dd/`)

### Architecture

```
┌─ Trading Bot ───────────────────────────────────┐
│                                                  │
│  DataCollector → Indicators → StrategyRegistry   │
│       │            (10개 전략, 시장 상태별 자동선택) │
│  Multi-Coin     bb_rsi_combined (횡보/하락)      │
│  Scanner        volatility_breakout (상승)       │
│       │                                          │
│  RiskManager ←── confidence + 수수료 가드        │
│       │                                          │
│  OrderExecutor (pyupbit, 멀티코인)               │
│       │                                          │
│  DataRecorder (signals + trades + params)        │
└──────┬───────────────────────────────────────────┘
       │
┌──────┴──────────── SQLite (공유 DB) ────────────┐
│  market_snapshots │ trade_signals │ trades       │
│  ohlcv_daily      │ news_articles │ llm_decisions│
│  bot_config       │ strategies    │ ...          │
└──────┬────────────┬───────────────┬──────────────┘
       │            │               │
┌──────┴──────┐ ┌───┴────────┐ ┌────┴─────────────┐
│ News        │ │ Watchdog   │ │ FastAPI + React   │
│ Collector   │ │            │ │ Admin Dashboard   │
│             │ │ 헬스체크    │ │                   │
│ RSS 크롤링   │ │ 에러 감시   │ │ 6개 페이지         │
│ Fear&Greed  │ │ Slack 알림  │ │ 전략/신호/설정     │
│ (30분 주기)  │ │ (5분 주기)  │ │                   │
└─────────────┘ └────────────┘ └───────────────────┘
       │
┌──────┴──────────────────────────────────────────┐
│ LLM Analyzer (Phase 2 — 기존 봇에 통합)          │
│                                                  │
│ 뉴스 분석 → 시장 심리 판단 → 파라미터 자동 조절    │
│ Claude Haiku │ 4시간 주기 │ llm_decisions 기록   │
│ 공포 기반 DCA │ 토큰 최적화 (~$0.004/일)          │
└──────────────────────────────────────────────────┘
       │
     Slack (Bot Token)
   매매 알림 + 에러 + 워치독
```
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Trading | pyupbit (Upbit API) |
| Data | pandas, numpy, SQLite |
| API Server | FastAPI + uvicorn |
| Dashboard | React 18 + TypeScript + Vite + Recharts |
| Notification | Slack Bot Token (slack_sdk) |
| Scheduling | APScheduler (10초 간격) |
| Logging | RotatingFileHandler (날짜별 분리) |
| LLM | Anthropic Claude Haiku (Phase 2) |
| Infra | Docker, Docker Compose (Phase 3) |

## Project Structure

```
cryptobot/
├── src/cryptobot/
│   ├── bot/                # 트레이딩 봇 코어
│   │   ├── main.py         # 진입점, 스케줄러 (10초 간격)
│   │   ├── config.py       # 설정 관리
│   │   ├── trader.py       # 주문 실행 (pyupbit)
│   │   ├── strategy.py     # 변동성 돌파 (레거시, 호환용)
│   │   ├── indicators.py   # 기술적 지표 (RSI, MA, BB, ATR)
│   │   ├── risk.py         # 리스크 관리 (confidence 기반 포지션 사이징)
│   │   └── scanner.py      # 종목 자동 선별
│   │
│   ├── strategies/         # 매매 전략 (Strategy Pattern)
│   │   ├── base.py         # BaseStrategy 인터페이스
│   │   ├── registry.py     # StrategyRegistry (시장 상태별 선택)
│   │   └── *.py            # 9개 전략 구현체
│   │
│   ├── data/               # 데이터 레이어
│   │   ├── database.py     # DB 스키마 + 마이그레이션
│   │   ├── collector.py    # 시장 데이터 수집 + OHLCV 저장
│   │   ├── recorder.py     # 매매/신호 기록 저장
│   │   └── strategy_repository.py  # 전략 DB 관리 (단일 활성화)
│   │
│   ├── api/                # FastAPI (Admin 백엔드)
│   │   └── routes/         # auth, balance, trades, strategies, signals, config
│   ├── notifier/           # Slack 알림 (Bot Token + Webhook 폴백)
│   ├── logging_config.py   # 에러 로깅 (날짜별 파일)
│   └── exceptions.py       # 공통 예외
│
├── admin/                  # React Admin 대시보드
│   └── src/
│       ├── pages/          # 6개 페이지 (대시보드, 매매, 전략, 신호, 수익, 설정)
│       ├── api/            # API 클라이언트
│       ├── utils/          # 포맷, 지표설명, 파라미터설명, 에러리포터
│       └── context/        # Auth 상태 관리
│
├── error/                  # 에러 로그 (날짜별 폴더, gitignore)
├── data/                   # SQLite DB (gitignore)
├── scripts/                # 유틸리티 (start_all.sh, create_admin.py 등)
├── tests/                  # 테스트 (65개)
└── Makefile                # make start/bot/api/web/test/lint
```

## Data Design

매매 판단의 입력(시장 상태)과 출력(매매 결과)을 함께 저장하여, LLM이 과거 데이터를 기반으로 전략을 개선할 수 있도록 설계했습니다. 모든 타임스탬프는 UTC 기준.

```
ohlcv_daily (매일 120일치 upsert)
    → 일봉 OHLCV 데이터 (백테스팅/LLM 학습용)

market_snapshots (10초 간격)
    → 시세, 거래량, 기술적 지표, 시장 상태 판단

trade_signals (매 틱마다)
    → 실행 여부 관계없이 모든 신호 기록 + 적용된 전략 파라미터 JSON

trades (체결 시)
    → 매매 시점의 파라미터 + 시장 상태 + 수익률 + 보유시간

bot_config (변경 시)
    → 봇/알림/리스크/전략 설정 (Admin에서 실시간 변경)

strategy_activations (전환 시)
    → 전략 활성화/비활성화/종료중 이력

daily_reports (자정)
    → 일일 정산 (승률, 수익률, 잔고)
```

## Quick Start

```bash
# 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate

# 패키지 설치
pip install -e ".[dev]"

# 환경변수 설정
cp .env.example .env
# .env 파일에 Upbit API Key, Slack Bot Token 입력

# Admin 웹 의존성 설치
cd admin && npm install && cd ..

# 관리자 계정 생성
python scripts/create_admin.py
```

### 바로 실행

```bash
# 전체 한번에 실행 (봇 + API 서버 + Admin 웹)
make start
# 또는
bash scripts/start_all.sh
```

Ctrl+C로 전체 종료. 로그에 `[BOT]`, `[API]`, `[WEB]` 태그로 구분됨.

- API 서버: http://localhost:8000
- Admin 대시보드: http://localhost:5173
- API 문서: http://localhost:8000/api/docs

### 개별 실행

```bash
make bot      # 봇만
make api      # API 서버만
make web      # Admin 웹만
make test     # 테스트
make lint     # 린트
```

## Admin Dashboard

| 페이지 | 기능 |
|---|---|
| 대시보드 | KPI, 포지션, 시장 현황, BTC 가격 추이 (1h~30d 기간 선택) |
| 매매 내역 | 매매 이력 필터/페이지네이션, 상세 모달 |
| 전략 관리 | 9개 전략 (시장별 섹션), 파라미터 편집 + AS-IS/TO-BE 시뮬레이션 |
| 매매 신호 | 실시간 신호 이력, 지표/파라미터 상세, 30초 자동 새로고침 |
| 수익률 분석 | 누적 수익 차트, 일별 PnL, 승/패 비율 |
| 설정 | 봇/알림/리스크/전략 설정 토글/입력 (변경 즉시 반영) |

## Development Roadmap

### Phase 1: MVP — 자동매매 기본 동작 (완료)

- [x] #1 프로젝트 초기 설정
- [x] #4 API Key 발급 + 연결 테스트
- [x] #5 설정 관리 모듈 (config.py)
- [x] #6 데이터베이스 초기화
- [x] #7 기술적 지표 계산 모듈
- [x] #8 변동성 돌파 전략 엔진 + 8개 추가 전략
- [x] #9 주문 실행 모듈
- [x] #10 시장 데이터 수집기
- [x] #11 Slack 알림 모듈
- [x] #12 메인 루프 + 스케줄러

### Phase 2: Admin 대시보드 + LLM 연동

**백엔드 API (FastAPI)**
- [x] #29 FastAPI 프로젝트 초기 설정
- [x] #30 JWT 인증 + 로그인 API
- [x] #31 매매 내역 API
- [x] #32 잔고 + 포지션 API
- [x] #33 전략 관리 API
- [x] #34 시장 현황 API

**프론트엔드 (React)**
- [x] #35 React Admin 프로젝트 초기 설정
- [x] #36 대시보드 페이지 — 전체 현황
- [x] #37 대시보드 페이지 — 매매 내역
- [x] #38 대시보드 페이지 — 전략 관리
- [x] #39 대시보드 페이지 — 수익률 분석
- [x] #44 Slack Bot Token 알림
- [x] #46 로그인 안정화 (thread-local DB)
- [x] #47 신호 강도 기반 포지션 사이징
- [x] #49 에러 로깅 시스템
- [x] #50 전략 레지스트리 봇 연결
- [x] #52 봇 설정 관리 + 틱별 Slack 리포트
- [x] #55 전략 단일 활성화 + 종료중 상태
- [x] #57 타임스탬프 UTC 통일 + OHLCV 히스토리

**LLM 연동**
- [ ] #16 뉴스 수집기 (RSS)
- [ ] #17 Claude Haiku 연동 — 시장분석
- [ ] #18 LLM 파라미터 튜닝 — 매매 결과 피드백
- [ ] #19 백테스트 엔진

### Phase 3: 인프라 — 컨테이너화

- [ ] #20 Docker 컨테이너화
- [ ] #21 SQLite → PostgreSQL 마이그레이션

### Phase 4: 클라우드 — 배포 + 오케스트레이션

- [ ] #22 Airflow DAG 설계
- [ ] #23 클라우드 배포 (Oracle/AWS)

## License

MIT License
