"""로깅 설정 모듈.

봇과 API 서버에서 공통으로 사용하는 로깅 설정.
- 콘솔: 전체 레벨 출력
- 파일: ERROR 이상만 error/ 폴더에 날짜별 저장 (RotatingFileHandler)
"""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# 프로젝트 루트의 error/ 폴더
_ERROR_DIR = Path(__file__).resolve().parent.parent.parent / "error"


def _get_today_dir() -> Path:
    """오늘 날짜의 에러 로그 디렉토리 반환."""
    today = datetime.now().strftime("%Y-%m-%d")
    day_dir = _ERROR_DIR / today
    day_dir.mkdir(parents=True, exist_ok=True)
    return day_dir


class DailyRotatingFileHandler(logging.Handler):
    """날짜별 폴더에 로그를 저장하는 핸들러.

    error/2026-04-03/bot.log 형식으로 저장.
    파일당 최대 10MB, 최대 5개 백업.
    """

    def __init__(self, filename: str, max_bytes: int = 10 * 1024 * 1024, backup_count: int = 5) -> None:
        super().__init__()
        self._filename = filename
        self._max_bytes = max_bytes
        self._backup_count = backup_count
        self._current_date: str = ""
        self._handler: RotatingFileHandler | None = None

    def _ensure_handler(self) -> RotatingFileHandler:
        """날짜가 바뀌면 새 핸들러 생성."""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._current_date or self._handler is None:
            if self._handler is not None:
                self._handler.close()
            day_dir = _ERROR_DIR / today
            day_dir.mkdir(parents=True, exist_ok=True)
            self._handler = RotatingFileHandler(
                str(day_dir / self._filename),
                maxBytes=self._max_bytes,
                backupCount=self._backup_count,
                encoding="utf-8",
            )
            self._handler.setFormatter(self.formatter)
            self._current_date = today
        return self._handler

    def emit(self, record: logging.LogRecord) -> None:
        try:
            handler = self._ensure_handler()
            handler.emit(record)
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        if self._handler is not None:
            self._handler.close()
        super().close()


def setup_logging(service: str, log_level: str = "INFO") -> None:
    """서비스별 로깅 설정.

    Args:
        service: 서비스 이름 ("bot" / "api")
        log_level: 콘솔 로그 레벨
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # 기존 핸들러 제거 (중복 방지)
    root_logger.handlers.clear()

    # 포맷
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    error_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d)\n"
        "  %(message)s\n"
        "  %(exc_text)s" if False else
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. 콘솔 핸들러 — 전체 레벨
    console = logging.StreamHandler()
    console.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    console.setFormatter(fmt)
    root_logger.addHandler(console)

    # 2. 에러 파일 핸들러 — ERROR 이상만
    error_handler = DailyRotatingFileHandler(f"{service}.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(error_fmt)
    root_logger.addHandler(error_handler)

    # 3. 전체 로그 파일 핸들러 — WARNING 이상
    warn_handler = DailyRotatingFileHandler(f"{service}_warn.log")
    warn_handler.setLevel(logging.WARNING)
    warn_handler.setFormatter(fmt)
    root_logger.addHandler(warn_handler)

    logging.getLogger(service).info("로깅 초기화: %s (콘솔=%s, 에러파일=error/<date>/%s.log)", service, log_level, service)
