# CryptoBot

AI 기반 코인 자동매매 시스템. 규칙 기반 매매 전략에 LLM(Claude) 시장분석을 결합하여 매매 파라미터를 자동 조절하는 개인용 트레이딩 봇.

## Overview

업비트 API를 통해 코인을 자동으로 매수/매도하고, 매매 데이터를 축적하여 전략을 지속적으로 개선하는 시스템입니다. 단순한 자동매매를 넘어, 데이터 수집 → 변환 → 분석 → 자동화를 아우르는 데이터 파이프라인으로 설계되었습니다.

### Core Features

- **자동매매**: 변동성 돌파 전략 + 트레일링 스탑 + 손절 관리
- **시장분석**: Claude Haiku API를 활용한 뉴스 기반 시장 상태 판단 (하루 4회)
- **파라미터 자동 조절**: LLM이 시장 상황과 과거 매매 성과를 분석하여 전략 파라미터를 동적으로 조절
- **데이터 파이프라인**: 시계열 시장 데이터 수집, 매매 신호/결과 기록, 일일 정산 자동화
- **모니터링**: Slack 실시간 알림 + Streamlit 대시보드

### Architecture

```
┌─ Trading Bot (Python) ──────────────────────────┐
│                                                  │
│  DataCollector → IndicatorEngine → StrategyEngine│
│                                          │       │
│  LLMAnalyzer (Claude Haiku) ──→ ParamTuner       │
│                                          │       │
│                                   OrderExecutor  │
│                                          │       │
│  DataRecorder ←──────────────────────────┘       │
│       │                                          │
│   SQLite/PostgreSQL                              │
└──────────────────────────────────────────────────┘
        │                    │
     Slack              Streamlit
   (alerts)           (dashboard)
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Trading | pyupbit (Upbit API) |
| Data | pandas, numpy, SQLite → PostgreSQL |
| LLM | Anthropic Claude Haiku 4.5 |
| Dashboard | Streamlit + Plotly |
| Notification | Slack Webhook |
| Scheduling | APScheduler → Airflow |
| Infra | Docker, Docker Compose |
| Cloud | Oracle Cloud Free Tier / AWS |

## Project Structure

```
cryptobot/
├── bot/                # 트레이딩 봇 코어
│   ├── main.py         # 진입점, 스케줄러
│   ├── config.py       # 설정 관리
│   ├── strategy.py     # 매매 전략 엔진
│   ├── trader.py       # 주문 실행
│   ├── indicators.py   # 기술적 지표
│   ├── scanner.py      # 종목 자동 선별
│   └── risk.py         # 리스크 관리
│
├── data/               # 데이터 레이어
│   ├── database.py     # DB 연결 관리
│   ├── collector.py    # 시장 데이터 수집
│   ├── recorder.py     # 매매/시장 기록 저장
│   └── models.py       # 데이터 모델
│
├── llm/                # LLM 분석 레이어
│   ├── analyzer.py     # Claude API 호출
│   ├── prompts.py      # 프롬프트 템플릿
│   ├── news_fetcher.py # 뉴스 수집
│   └── param_tuner.py  # 파라미터 최적화
│
├── notifier/           # 알림
│   └── slack.py        # Slack 알림/리포트
│
├── dashboard/          # Admin 대시보드
│   ├── app.py          # Streamlit 메인
│   └── pages/          # 대시보드 페이지
│
├── backtest/           # 백테스트 엔진
│   ├── engine.py       # 시뮬레이션
│   └── optimizer.py    # 파라미터 최적화
│
├── scripts/            # 유틸리티
├── tests/              # 테스트
└── docs/               # 문서
    └── work/           # 개발 작업 문서
```

## Data Design

매매 판단의 입력(시장 상태)과 출력(매매 결과)을 함께 저장하여, LLM이 과거 데이터를 기반으로 전략을 개선할 수 있도록 설계했습니다.

```
market_snapshots (1분 간격)
    → 시세, 거래량, 기술적 지표, 시장 상태 판단

trade_signals (매매 신호 발생 시)
    → 실행 여부 관계없이 모든 신호 기록

trades (체결 시)
    → 매매 시점의 파라미터 + 시장 상태 + 결과

strategy_params (변경 시)
    → 파라미터 이력 + 적용 기간 성과

llm_decisions (하루 4회)
    → LLM 입출력 전체 + 사후 성과 평가
```

## Quick Start

```bash
# 가상환경 생성
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일에 API Key 입력

# DB 초기화
python scripts/setup_db.py

# 봇 실행
python bot/main.py

# 대시보드 실행 (별도 터미널)
streamlit run dashboard/app.py
```

## Development Roadmap

- **Phase 1**: MVP — 변동성 돌파 전략, 단일 종목 자동매매, Slack 알림
- **Phase 2**: LLM 연동 — Claude Haiku 시장분석, 멀티 종목, 백테스트, 대시보드
- **Phase 3**: 컨테이너화 — Docker, PostgreSQL, dbt
- **Phase 4**: 클라우드 — Oracle Cloud/AWS 배포, Airflow 오케스트레이션

## License

MIT License
