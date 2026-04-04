# CryptoBot

AI 기반 코인 자동매매 시스템. 10개 매매 전략 + Claude AI 시장분석을 결합하여 매매 파라미터를 자동 조절하는 개인용 트레이딩 봇.

## Overview

업비트 API를 통해 멀티코인을 자동으로 매수/매도하고, 뉴스 수집 + AI 분석으로 전략을 지속 개선하는 시스템입니다. 데이터 수집 → 변환 → AI 분석 → 자동 매매를 아우르는 데이터 파이프라인으로 설계되었습니다.

### Core Features

- **10개 매매 전략**: 볼린저+RSI 복합, 변동성 돌파, RSI, MACD 등 (시장 상태별 자동 선택)
- **멀티코인**: 거래량/변동성 기반 자동 선별 (BTC/ETH/XRP 고정 + 알트코인 자동)
- **AI 시장분석**: Claude Haiku가 4시간마다 뉴스 분석 → 전략/파라미터 자동 조절
- **뉴스 수집**: CoinDesk, CoinTelegraph RSS + Fear & Greed Index (30분 주기)
- **리스크 관리**: 수수료 가드, 손절/트레일링 스탑, 하드 리밋 (AI 조절 범위 제한)
- **프롬프트 버전 관리**: AI 판단 이력 + 프롬프트별 성과 추적
- **React Admin 대시보드**: 8개 페이지 (대시보드, 매매, 전략, 신호, 뉴스, 수익, LLM, 설정)
- **에러 로깅**: 날짜별 분리 + AI 비용 트래킹

### Architecture

```
┌─ Trading Bot ───────────────────────────────────┐
│  Multi-Coin Scanner → DataCollector (60초)       │
│  StrategyRegistry (10개, 시장 상태별 자동선택)     │
│  RiskManager (수수료 가드 + 하드 리밋)            │
│  LLM Analyzer (4시간) → 파라미터 자동 조절        │
│  OrderExecutor (pyupbit)                         │
└──────┬───────────────────────────────────────────┘
       │
┌──────┴────────── SQLite (공유 DB) ──────────────┐
│  market_snapshots │ trade_signals │ trades       │
│  ohlcv_daily      │ news_articles │ llm_decisions│
│  prompt_versions  │ fear_greed    │ bot_config   │
└──────┬────────────┬──────────────────────────────┘
       │            │
┌──────┴──────┐ ┌───┴────────────────────────────┐
│ News        │ │ FastAPI + React Admin (8페이지)  │
│ Collector   │ │ 대시보드/매매/전략/신호/뉴스      │
│ RSS + F&G   │ │ 수익분석/LLM관리/설정            │
│ (30분 주기)  │ │                                │
└─────────────┘ └────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Trading | pyupbit (Upbit API, 현물 매매) |
| Data | pandas, numpy, SQLite |
| LLM | Anthropic Claude Haiku 4.5 (~월 640원) |
| API Server | FastAPI + uvicorn |
| Dashboard | React 18 + TypeScript + Vite |
| News | RSS (CoinDesk, CoinTelegraph) + Fear & Greed API |
| Notification | Slack Bot Token (slack_sdk) |
| Scheduling | APScheduler |
| Logging | RotatingFileHandler (날짜별 분리) |
| Tests | pytest (90건) |

## Project Structure

```
cryptobot/
├── src/cryptobot/
│   ├── bot/                # 트레이딩 봇 코어
│   │   ├── main.py         # 메인 루프 (60초 틱 + LLM 4시간)
│   │   ├── trader.py       # 주문 실행 (pyupbit)
│   │   ├── risk.py         # 리스크 관리 (수수료 가드 + 하드 리밋)
│   │   ├── scanner.py      # 멀티코인 자동 선별
│   │   └── indicators.py   # 기술적 지표
│   │
│   ├── strategies/         # 매매 전략 (10개)
│   │   ├── bb_rsi_combined.py  # 볼린저+RSI 복합 (주력)
│   │   ├── volatility_breakout.py
│   │   └── ...             # 총 10개 전략
│   │
│   ├── llm/                # AI 분석
│   │   └── analyzer.py     # Claude 시장분석 + 파라미터 조절
│   │
│   ├── data/               # 데이터 레이어
│   │   ├── database.py     # DB 스키마 + 인덱스 + 마이그레이션
│   │   ├── collector.py    # 시장 데이터 수집 (OHLCV 캐시)
│   │   └── recorder.py     # 매매/신호 기록
│   │
│   ├── api/routes/         # FastAPI (Admin 백엔드)
│   │   ├── trades, signals, strategies, config
│   │   ├── news, market, balance
│   │   └── llm (decisions, prompts, hard-limits)
│   │
│   ├── notifier/           # Slack 알림
│   └── logging_config.py   # 에러 로깅
│
├── news-collector/         # 뉴스 수집기 (별도 프로세스)
│   ├── collector.py        # 메인 (30분 주기)
│   └── sources/            # RSS, Fear&Greed, 업비트
│
├── admin/                  # React Admin 대시보드 (8페이지)
├── error/                  # 에러 로그 (날짜별)
├── tests/                  # 테스트 (90건)
└── Makefile                # make start/bot/api/web/news/test
```

## Data Design

모든 타임스탬프는 UTC (`YYYY-MM-DD HH:MM:SS`). 매매 판단의 전체 흐름(뉴스 → AI 분석 → 전략 선택 → 매매 → 성과)을 추적 가능하도록 설계.

```
news_articles (30분) → 뉴스 원문 + 코인 태깅 + 감성 분류
fear_greed_index (1시간) → 공포/탐욕 지수

llm_decisions (4시간) → AI 시장 요약(한국어) + 파라미터 변경 + 비용
prompt_versions → 프롬프트 전문 + 버전 관리 + 성과 연결

market_snapshots (60초, 멀티코인) → 코인별 시세 + 지표 + 시장 상태
ohlcv_daily (매일) → 120일 일봉 (백테스팅/학습용)
trade_signals (매 틱) → 매수/매도/HOLD 판단 + 파라미터 JSON
trades (체결 시) → 수익률(수수료 포함) + 보유시간 + 전략

bot_config → 실시간 설정 (Admin에서 변경)
strategy_activations → 전략 전환 이력
daily_reports (자정) → 일일 정산
```

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # API Key, Slack, LLM 설정
cd admin && npm install && cd ..
python scripts/create_admin.py
```

### 실행

```bash
# 전체 (봇 + API + 뉴스 수집기 + Admin)
make start

# 개별
make bot      # 트레이딩 봇
make api      # API 서버 (localhost:8000)
make web      # Admin (localhost:5173)
make news     # 뉴스 수집기
make test     # 테스트 (90건)
```

## Admin Dashboard

| 페이지 | 기능 |
|---|---|
| 대시보드 | KPI(자산/손익%), 포지션, AI 시장 요약, 최근 매매, 모니터링 코인 |
| 매매 내역 | 시간순 매매 이력, 신뢰도, 순수익(수수료 포함) |
| 전략 관리 | 10개 전략 카드, 코인별 적용 현황, 파라미터 편집 + 시뮬레이션 |
| 매매 신호 | 실시간 신호 이력, 지표/파라미터 상세, 30초 자동 갱신 |
| 뉴스 | RSS 뉴스 + 공포/탐욕 지수, 감성 필터, 코인 검색 |
| 수익률 분석 | 승률, 매도 수익 합계, 총 수수료 |
| LLM 관리 | AI 모델/비용/프롬프트 히스토리, 분석 이력(before/after) |
| 설정 | 봇/리스크/알림/코인 설정 + LLM 하드 리밋 (읽기 전용) |

## Development Roadmap

### Phase 1: MVP — 자동매매 기본 동작 (완료)

- [x] #1~#12 프로젝트 설정, DB, 지표, 전략, 주문, 수집, 알림, 스케줄러

### Phase 2: Admin + AI 연동 (완료)

- [x] #29~#39 FastAPI + React Admin 대시보드 (8페이지)
- [x] #44~#68 멀티코인, 볼린저+RSI 복합, 수수료 가드, 최적화, 통합 테스트
- [x] #16 뉴스 수집기 (RSS + Fear & Greed)
- [x] #17 Claude Haiku 연동 — AI 시장분석 + 파라미터 자동 조절
- [x] #18 프롬프트 버전 관리 + 과거 성과 기반 튜닝
- [ ] #19 백테스트 엔진 (ohlcv_daily 활용)
- [ ] #70 워치독 서비스

### Phase 3: 인프라

- [ ] #20 Docker 컨테이너화
- [ ] #21 SQLite → PostgreSQL 마이그레이션

### Phase 4: 클라우드 + 고도화

- [ ] #22 Airflow DAG 설계
- [ ] #23 클라우드 배포
- [ ] #78 매매 판단 데이터 분석 파이프라인
- [ ] #79 자체 LLM 파인튜닝

## License

MIT License
