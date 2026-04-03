# CryptoBot

AI 기반 코인 자동매매 시스템. 규칙 기반 매매 전략에 LLM(Claude) 시장분석을 결합하여 매매 파라미터를 자동 조절하는 개인용 트레이딩 봇.

## Overview

업비트 API를 통해 코인을 자동으로 매수/매도하고, 매매 데이터를 축적하여 전략을 지속적으로 개선하는 시스템입니다. 단순한 자동매매를 넘어, 데이터 수집 → 변환 → 분석 → 자동화를 아우르는 데이터 파이프라인으로 설계되었습니다.

### Core Features

- **자동매매**: 변동성 돌파 전략 + 트레일링 스탑 + 손절 관리
- **시장분석**: Claude Haiku API를 활용한 뉴스 기반 시장 상태 판단 (하루 4회)
- **파라미터 자동 조절**: LLM이 시장 상황과 과거 매매 성과를 분석하여 전략 파라미터를 동적으로 조절
- **데이터 파이프라인**: 시계열 시장 데이터 수집, 매매 신호/결과 기록, 일일 정산 자동화
- **모니터링**: Slack 실시간 알림 + React Admin 대시보드

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
| API Server | FastAPI + uvicorn |
| Dashboard | React + TypeScript + Vite |
| Notification | Slack Webhook |
| Scheduling | APScheduler → Airflow |
| Infra | Docker, Docker Compose |
| Cloud | Oracle Cloud Free Tier / AWS |

## Project Structure

```
cryptobot/
├── src/cryptobot/
│   ├── bot/                # 트레이딩 봇 코어
│   │   ├── main.py         # 진입점, 스케줄러
│   │   ├── config.py       # 설정 관리
│   │   ├── trader.py       # 주문 실행
│   │   ├── indicators.py   # 기술적 지표
│   │   ├── scanner.py      # 종목 자동 선별
│   │   └── risk.py         # 리스크 관리
│   │
│   ├── strategies/         # 매매 전략 (Strategy Pattern)
│   │   ├── base.py         # 전략 인터페이스
│   │   ├── registry.py     # 전략 등록/선택
│   │   └── *.py            # 9개 전략 구현체
│   │
│   ├── data/               # 데이터 레이어
│   │   ├── database.py     # DB 연결 + 스키마
│   │   ├── collector.py    # 시장 데이터 수집
│   │   ├── recorder.py     # 매매/시장 기록 저장
│   │   └── strategy_repository.py  # 전략 DB 관리
│   │
│   ├── api/                # FastAPI 웹 서버 (Admin 백엔드)
│   ├── notifier/           # Slack 알림
│   └── exceptions.py       # 공통 예외
│
├── admin/                  # React Admin 대시보드
├── tests/                  # 테스트
├── scripts/                # 유틸리티
└── docs/work/              # 개발 작업 문서
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
python3 -m venv .venv
source .venv/bin/activate

# 패키지 설치
pip install -e ".[dev]"

# 환경변수 설정
cp .env.example .env
# .env 파일에 API Key 입력

# DB 초기화
python scripts/setup_db.py

# 봇 실행
python -m cryptobot

# API 서버 실행 (별도 터미널)
uvicorn cryptobot.api.main:app --reload --port 8000

# Admin 대시보드 (별도 터미널)
cd admin && npm run dev
```

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
- [ ] #29 FastAPI 프로젝트 초기 설정
- [ ] #30 JWT 인증 + 로그인 API
- [ ] #31 매매 내역 API
- [ ] #32 잔고 + 포지션 API
- [ ] #33 전략 관리 API
- [ ] #34 시장 현황 API

**프론트엔드 (React)**
- [ ] #35 React Admin 프로젝트 초기 설정
- [ ] #36 대시보드 페이지 — 전체 현황
- [ ] #37 대시보드 페이지 — 매매 내역
- [ ] #38 대시보드 페이지 — 전략 관리
- [ ] #39 대시보드 페이지 — 수익률 분석

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
