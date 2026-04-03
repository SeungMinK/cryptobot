"""FastAPI 서버 진입점.

NestJS의 main.ts (bootstrap) + AppModule과 동일.

사용법:
    uvicorn cryptobot.api.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from cryptobot.api.routes import auth, balance, config, market, strategies, trades

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


@app.get("/api/health", tags=["system"])
def health_check():
    """헬스체크. 서버가 살아있는지 확인."""
    return {"status": "ok", "service": "cryptobot-api"}
