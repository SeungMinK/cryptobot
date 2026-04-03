"""인증 라우트.

NestJS의 AuthController와 동일.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from cryptobot.api.auth import (
    TokenResponse,
    UserResponse,
    create_access_token,
    get_current_user,
    verify_password,
)
from cryptobot.api.deps import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """로그인 → JWT 토큰 발급."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE username = ?", (form_data.username,)).fetchone()

    if row is None or not verify_password(form_data.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="아이디 또는 비밀번호가 올바르지 않습니다",
        )

    # 마지막 로그인 시간 업데이트
    db.execute(
        "UPDATE users SET last_login_at = ? WHERE id = ?",
        (datetime.now(timezone.utc).isoformat(), row["id"]),
    )
    db.commit()

    token = create_access_token(data={"sub": row["username"]})
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserResponse = Depends(get_current_user)):
    """현재 로그인한 유저 정보."""
    return current_user
