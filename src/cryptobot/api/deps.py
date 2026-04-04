"""FastAPI 의존성 주입.

NestJS의 @Inject() + providers와 동일한 역할.
DB 커넥션, Repository 등을 라우트에 주입한다.
"""

import threading
from functools import lru_cache

from cryptobot.bot.config import config
from cryptobot.data.database import Database
from cryptobot.data.recorder import DataRecorder
from cryptobot.data.strategy_repository import StrategyRepository

_thread_local = threading.local()
_test_db_override: Database | None = None


def get_db() -> Database:
    """스레드별 DB 커넥션. FastAPI 워커 스레드에서 안전하게 사용."""
    if _test_db_override is not None:
        return _test_db_override
    if not hasattr(_thread_local, "db") or _thread_local.db is None:
        _thread_local.db = Database(config.bot.db_path)
        _thread_local.db.initialize()
    return _thread_local.db


def get_recorder() -> DataRecorder:
    return DataRecorder(get_db())


def get_strategy_repo() -> StrategyRepository:
    return StrategyRepository(get_db())


@lru_cache
def get_jwt_secret() -> str:
    """JWT 시크릿 키. .env의 JWT_SECRET 또는 기본값."""
    import os

    return os.getenv("JWT_SECRET", "cryptobot-dev-secret-change-in-production")
