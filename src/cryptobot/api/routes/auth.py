"""인증 라우트.

NestJS의 AuthController와 동일.
"""

import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from cryptobot.api.auth import (
    TokenResponse,
    UserResponse,
    create_access_token,
    get_current_user,
    verify_password,
)
from cryptobot.api.deps import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

# 로그인 rate limit (IP당 5회/분)
_login_attempts: dict[str, list[float]] = defaultdict(list)
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60


@router.post("/login", response_model=TokenResponse)
def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """로그인 → JWT 토큰 발급."""
    client_ip = request.client.host if request.client else "unknown"

    # rate limit 체크
    now = time.time()
    _login_attempts[client_ip] = [t for t in _login_attempts[client_ip] if now - t < LOGIN_WINDOW_SECONDS]
    if len(_login_attempts[client_ip]) >= LOGIN_MAX_ATTEMPTS:
        logger.warning("로그인 rate limit 초과: %s", client_ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도 횟수 초과. 1분 후 다시 시도하세요.",
        )
    _login_attempts[client_ip].append(now)

    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (form_data.username,)).fetchone()

    if row is None or not verify_password(form_data.password, row["password_hash"]):
        logger.warning("로그인 실패: user=%s ip=%s", form_data.username, client_ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
        )

    # 마지막 로그인 시간 업데이트
    db.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"), row["id"]),
    )
    db.commit()

    token = create_access_token(data={"sub": row["username"]})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserResponse = Depends(get_current_user)):
    """현재 로그인한 유저 정보."""
    return current_user
