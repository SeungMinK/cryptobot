"""FastAPI 서버 진입점.

NestJS의 main.ts (bootstrap) + AppModule과 동일.

사용법:
    uvicorn cryptobot.api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cryptobot.api.routes import auth, balance, config, market, signals, strategies, trades
from cryptobot.logging_config import setup_logging

setup_logging("api", "INFO")

app = FastAPI(
    title="CryptoBot Admin API",
    description="코인 자동매매 봇 관리 API",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# CORS — React dev 서버 (localhost:5173) 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우트 등록 — NestJS의 imports: [AuthModule, TradeModule, ...]
app.include_router(auth.router)
app.include_router(trades.router)
app.include_router(balance.router)
app.include_router(strategies.router)
app.include_router(market.router)
app.include_router(config.router)
app.include_router(signals.router)


@app.get("/api/health", tags=["system"])
def health_check():
    """헬스체크. 서버가 살아있는지 확인."""
    return {"status": "ok", "service": "cryptobot-api"}


import logging as _logging

_web_logger = _logging.getLogger("web")


from pydantic import BaseModel as _BaseModel


class _WebErrorReport(_BaseModel):
    message: str
    source: str | None = None
    stack: str | None = None
    url: str | None = None
    user_agent: str | None = None


@app.post("/api/error/report", tags=["system"])
def report_web_error(error: _WebErrorReport):
    """Admin 웹에서 발생한 에러를 서버 로그로 기록."""
    _web_logger.error(
        "[WEB] %s | source=%s | url=%s\n  %s",
        error.message,
        error.source or "unknown",
        error.url or "unknown",
        error.stack or "no stack",
    )
    return {"status": "recorded"}
