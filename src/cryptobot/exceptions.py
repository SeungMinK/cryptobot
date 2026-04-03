"""프로젝트 공통 예외 클래스."""


class CryptoBotError(Exception):
    """CryptoBot 기본 예외."""


class ConfigError(CryptoBotError):
    """설정 관련 에러 (API Key 미설정 등)."""


class DatabaseError(CryptoBotError):
    """데이터베이스 관련 에러."""


class InsufficientBalanceError(CryptoBotError):
    """잔고 부족."""


class OrderError(CryptoBotError):
    """주문 실행 실패."""


class APIError(CryptoBotError):
    """외부 API 호출 실패 (업비트, Claude, Slack)."""
