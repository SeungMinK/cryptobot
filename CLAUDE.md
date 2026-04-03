# CryptoBot — Claude 작업 가이드

## 프로젝트 개요

업비트 API 기반 코인 자동매매 봇. 변동성 돌파 전략 + Claude Haiku 시장분석.
상세 설계는 `docs/work/docs-work-README.md` 참조.

## 기술 스택

- Python 3.11+
- SQLite (Phase 1) → PostgreSQL (Phase 3)
- pyupbit, pandas, numpy
- APScheduler, Slack Webhook, Streamlit

## 프로젝트 구조

```
src/cryptobot/
├── bot/            # 트레이딩 코어
├── data/           # DB, 수집, 기록
├── llm/            # Claude 연동 (Phase 2)
├── notifier/       # Slack 알림
├── dashboard/      # Streamlit (Phase 2)
├── backtest/       # 백테스트 (Phase 2)
└── scripts/        # 유틸리티
tests/              # 테스트 (src 구조 미러링)
```

## 코드 컨벤션

### 스타일

- 포매터: ruff format (line-length=120)
- 린터: ruff (rules: E, F, I)
- 따옴표: 큰따옴표 `"` 사용
- 들여쓰기: 스페이스 4칸
- 네이밍: snake_case (함수/변수), PascalCase (클래스), UPPER_SNAKE_CASE (상수)
- import 순서: 표준 라이브러리 → 서드파티 → 프로젝트 내부 (ruff I 룰이 자동 정렬)

### 타입 힌트

- 모든 함수의 파라미터와 리턴 타입에 타입 힌트 작성
- `Optional[X]` 대신 `X | None` 사용 (Python 3.10+ 스타일)

```python
def calculate_rsi(prices: list[float], period: int = 14) -> float | None:
    ...
```

### 독스트링

- 모듈, 클래스, public 함수에 docstring 작성
- Google 스타일 docstring 사용

```python
def place_order(coin: str, side: str, amount: float) -> dict:
    """업비트에 주문을 실행한다.

    Args:
        coin: 종목 코드 (예: "KRW-BTC")
        side: 매수/매도 ("buy" / "sell")
        amount: 주문 수량

    Returns:
        업비트 API 응답 dict

    Raises:
        InsufficientBalanceError: 잔고 부족 시
    """
```

### 에러 처리

- API 호출(업비트, Claude, Slack)은 반드시 try/except로 감싸기
- 자체 예외 클래스는 `src/cryptobot/exceptions.py`에 정의
- 봇이 죽지 않도록 최상위 루프에서 catch-all 처리, 에러 시 Slack 알림

### 로깅

- `print()` 금지. 반드시 `logging` 모듈 사용
- 로그 레벨: DEBUG(지표 계산), INFO(매매 체결), WARNING(재시도), ERROR(API 실패)

```python
import logging
logger = logging.getLogger(__name__)
```

### 설정 관리

- 시크릿(API Key 등): `.env` 파일 → 절대 커밋 금지
- 매매 파라미터: DB `strategy_params` 테이블에서 로딩
- 앱 설정(로그 레벨, 스케줄 주기 등): `config.py`

### 테스트

- 테스트 프레임워크: pytest
- 테스트 파일: `tests/` 디렉토리에 `test_*.py`
- API 호출이 필요한 테스트는 mock 사용 (실제 API 호출 금지)
- 매매 전략 로직은 반드시 단위 테스트 작성

### DB

- ORM 사용하지 않음. 직접 SQL 작성 (sqlite3 모듈)
- 테이블 스키마: `docs/work/docs-work-README.md`에 정의된 스키마를 그대로 사용
- 마이그레이션: `scripts/` 디렉토리에 SQL 스크립트로 관리

### Git 규칙

- 브랜치: `feature/{기능명}`, `fix/{버그명}`, `refactor/{대상}`
- 커밋 메시지: `feat:`, `fix:`, `refactor:`, `test:`, `docs:` 접두사 사용
- 이슈 번호 연결: 커밋 메시지에 `(#이슈번호)` 포함
- PR은 관련 이슈에 `Related: #번호`로 연결

## 작업 시 주의사항

- 업비트 API Key는 **출금 권한 없이** 발급
- 실매매 코드 수정 시 반드시 백테스트 또는 테스트 먼저 실행
- 금액/수량 계산에서 부동소수점 주의 (Decimal 사용 검토)
- 모든 시간은 KST(Asia/Seoul) 기준으로 처리
