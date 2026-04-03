# CryptoBot 컨벤션

> 프로젝트의 코드, Git, 네이밍, 구조 등 모든 규칙을 정리한 문서입니다.
> 새 작업 시작 전에 반드시 확인하세요.

---

## Git

### 브랜치 네이밍

```
{이슈번호}/{타입}/{설명}
```

| 타입 | 용도 | 예시 |
|------|------|------|
| `feature` | 새 기능 | `29/feature/fastapi-setup` |
| `fix` | 버그 수정 | `42/fix/rsi-calculation` |
| `refactor` | 리팩토링 | `15/refactor/strategy-interface` |
| `docs` | 문서 | `1/docs/conventions` |
| `chore` | 설정/빌드 | `1/chore/gitignore-update` |

### 커밋 메시지

```
{타입}: {설명} (#{이슈번호})

본문 (선택)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
```

| 타입 | 용도 |
|------|------|
| `feat` | 새 기능 |
| `fix` | 버그 수정 |
| `refactor` | 리팩토링 (기능 변경 없음) |
| `test` | 테스트 추가/수정 |
| `docs` | 문서 |
| `chore` | 설정, 빌드, 의존성 |
| `style` | 포맷팅 (코드 변경 없음) |

예시:
```
feat: FastAPI 프로젝트 초기 설정 (#29)
fix: RSI 계산 시 데이터 부족 에러 (#42)
docs: 컨벤션 문서 작성 (#1)
```

### PR

- 제목: 커밋 메시지와 동일한 형식
- 본문: `Related: #{이슈번호}` 로 연결 (자동 닫힘 방지)
- 머지 후: 관련 이슈에 완료 코멘트 후 Close

### 브랜치 전략

```
main (보호)
 └── {이슈번호}/{타입}/{설명}  ← 작업 브랜치
      └── PR → main
```

- `main`에 직접 커밋 금지
- 모든 작업은 이슈 생성 → 브랜치 → PR → 머지
- 머지 후 브랜치 삭제

---

## Python 코드

### 스타일

| 항목 | 규칙 |
|------|------|
| 포매터 | `ruff format` (line-length=120) |
| 린터 | `ruff` (rules: E, F, I) |
| 따옴표 | 큰따옴표 `"` |
| 들여쓰기 | 스페이스 4칸 |
| 네이밍 | snake_case (함수/변수), PascalCase (클래스), UPPER_SNAKE_CASE (상수) |
| import 순서 | 표준 라이브러리 → 서드파티 → 프로젝트 (ruff I 룰 자동 정렬) |

### 타입 힌트

- 모든 함수의 파라미터와 리턴 타입에 타입 힌트 필수
- `Optional[X]` 대신 `X | None` 사용 (Python 3.10+ 스타일)

```python
def calculate_rsi(prices: list[float], period: int = 14) -> float | None:
    ...
```

### 독스트링

- 모듈, 클래스, public 함수에 docstring 작성
- Google 스타일

```python
def place_order(coin: str, side: str, amount: float) -> dict:
    """업비트에 주문을 실행한다.

    Args:
        coin: 종목 코드 (예: "KRW-BTC")
        side: 매수/매도 ("buy" / "sell")
        amount: 주문 수량

    Returns:
        업비트 API 응답 dict
    """
```

### 로깅

- `print()` 금지, `logging` 모듈만 사용
- 레벨: DEBUG(지표), INFO(매매 체결), WARNING(재시도), ERROR(API 실패)

```python
import logging
logger = logging.getLogger(__name__)
```

### 에러 처리

- 외부 API 호출(업비트, Claude, Slack)은 반드시 try/except
- 자체 예외는 `exceptions.py`에 정의
- 봇이 죽지 않도록 최상위 루프에서 catch-all + Slack 알림

### 테스트

- 프레임워크: pytest
- 파일: `tests/test_*.py`
- API 호출 테스트는 mock 사용
- 매매 전략 로직은 반드시 단위 테스트 작성
- 커밋 전 `pytest -v` + `ruff check .` 통과 필수

---

## 프로젝트 구조

```
cryptobot/
├── src/cryptobot/           # Python 소스
│   ├── bot/                 # 매매 봇 코어
│   ├── strategies/          # 매매 전략 (Strategy Pattern)
│   ├── data/                # DB, 수집, 기록
│   ├── notifier/            # Slack 알림
│   ├── api/                 # FastAPI 웹 서버 (Admin 백엔드)
│   └── exceptions.py        # 공통 예외
│
├── admin/                   # React Admin 대시보드
│   ├── src/
│   └── package.json
│
├── tests/                   # 테스트
├── scripts/                 # 유틸리티 스크립트
├── data/                    # DB 파일 (gitignore)
├── docs/work/               # 개발 작업 문서
│
├── CLAUDE.md                # Claude 작업 가이드 (자동 로드)
├── CONVENTIONS.md           # 이 파일 (컨벤션)
├── pyproject.toml           # Python 프로젝트 설정
├── .env                     # 환경변수 (gitignore)
└── .env.local               # 환경변수 키 공유용
```

---

## DB

- ORM 사용하지 않음, 직접 SQL (sqlite3 모듈)
- 스키마: `docs/work/docs-work-README.md` + `database.py`의 `_SCHEMA`
- Phase 1~2: SQLite, Phase 3: PostgreSQL 전환
- 시크릿은 `.env` → DB에 절대 저장 금지
- 시간은 KST (Asia/Seoul) 기준

---

## 전략 (Strategy)

### 새 전략 추가 방법

1. `src/cryptobot/strategies/` 에 파일 생성
2. `BaseStrategy` 상속, `info()`, `check_buy()`, `check_sell()` 구현
3. `database.py`의 `_DEFAULT_STRATEGIES`에 메타 정보 추가
4. `tests/test_strategies.py`에 테스트 추가
5. `strategies/README.md`에 설명 추가

### 전략 파일 구조

```python
class MyStrategy(BaseStrategy):
    def info(self) -> StrategyInfo: ...       # 메타 정보
    def check_buy(self, df, price) -> Signal: ...  # 매수 판단
    def check_sell(self, df, price, buy_price) -> Signal: ...  # 매도 판단
```

---

## Admin (React)

### 기술 스택

- React 18 + TypeScript
- Vite (빌드)
- React Router (라우팅)
- Axios (API 호출)
- Recharts (차트)

### API 통신

- 베이스 URL: `http://localhost:8000/api`
- 인증: JWT Bearer Token
- 에러 응답: `{ "detail": "에러 메시지" }`

---

## 환경변수

| 변수 | 용도 | 필수 |
|------|------|------|
| `UPBIT_ACCESS_KEY` | 업비트 API Key | 실매매 시 |
| `UPBIT_SECRET_KEY` | 업비트 Secret Key | 실매매 시 |
| `SLACK_WEBHOOK_URL` | Slack 알림 | 선택 |
| `BOT_COIN` | 매매 종목 (기본: KRW-BTC) | 선택 |
| `BOT_LOG_LEVEL` | 로그 레벨 (기본: INFO) | 선택 |
| `DB_PATH` | DB 경로 (기본: data/cryptobot.db) | 선택 |
| `JWT_SECRET` | JWT 시크릿 키 | Admin 사용 시 |
