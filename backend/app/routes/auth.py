from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from os import getenv
from fastapi.security import OAuth2PasswordBearer
from loguru import logger
from pydantic import BaseModel, EmailStr
import secrets
import sys

from app.db.models import UserModel, RefreshTokenModel, PasswordResetTokenModel
from app.db.session import get_db
from app.core.hashing import hash_password, verify_password
from app.db.schemas import UserSignupRequest, UserLoginRequest, TokenResponse, RefreshTokenRequest, ChangePasswordRequest, ForgotPasswordRequest, ResetPasswordRequest

SECRET_KEY = getenv("SECRET_KEY")
REFRESH_SECRET_KEY = getenv("REFRESH_SECRET_KEY", SECRET_KEY)
ALGORITHM = getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = 90
REFRESH_TOKEN_EXPIRE_DAYS = 30
RESET_TOKEN_EXPIRE_MINUTES = 15

_missing = [k for k in ("SECRET_KEY", "ALGORITHM") if not getenv(k)]
if _missing:
    logger.critical(f"Missing required environment variables: {_missing}. Refusing to start.")
    raise RuntimeError(f"Missing env vars: {_missing}")

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _user_context(user: UserModel) -> dict:
    """Reusable user payload kept identical to the existing frontend contract."""
    return {"id": user.id, "name": user.name, "email": user.email}


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = _utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["type"] = "access"
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# ── Dependency (exported for use in other routers) ────────────────────────────
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "access":
            logger.warning("Non-access token supplied to protected endpoint")
            raise credentials_exception

        user_id: str = payload.get("sub")
        if user_id is None:
            logger.warning(f"JWT missing 'sub' | payload={payload}")
            raise credentials_exception

    except JWTError as e:
        logger.error(f"Token decode failed: {e}")
        raise credentials_exception
    except Exception as e:
        logger.exception(f"Unexpected token validation error: {e}")
        raise credentials_exception

    try:
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if user is None:
            logger.warning(f"Authenticated user not found in DB | user_id={user_id}")
            raise credentials_exception
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"DB query failed for user_id={user_id}: {e}")
        raise credentials_exception

    return user


create_token = create_access_token
def create_refresh_token(user_id: int, db: Session) -> str:
    """
    Generates a signed refresh token, persists it to DB, and returns the raw token.
    Limits each user to 5 active refresh tokens (oldest revoked automatically).
    """
    raw = secrets.token_urlsafe(64)
    hashed = hash_password(raw)
    expires_at = _utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    # Enforce per-user token cap — revoke oldest if over limit
    existing = (
        db.query(RefreshTokenModel)
        .filter(RefreshTokenModel.user_id == user_id, RefreshTokenModel.revoked == False)  # noqa: E712
        .order_by(RefreshTokenModel.created_at.asc())
        .all()
    )
    if len(existing) >= 5:
        for old in existing[: len(existing) - 4]:
            old.revoked = True
            logger.info(f"Auto-revoked oldest refresh token | user_id={user_id} | token_id={old.id}")

    record = RefreshTokenModel(
        user_id=user_id,
        token_hash=hashed,
        expires_at=expires_at,
        revoked=False,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    logger.debug(f"Refresh token created | user_id={user_id} | token_id={record.id}")
    return raw


@router.post("/sign-up", status_code=status.HTTP_201_CREATED)
def sign_up(request: UserSignupRequest, req: Request, db: Session = Depends(get_db)):
    log = logger.bind(endpoint="sign_up", ip=req.client.host, email=request.email)
    log.info("Sign-up attempt")

    existing_user = db.query(UserModel).filter(UserModel.email == request.email).first()
    if existing_user:
        log.warning("Sign-up rejected — email already registered")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already registered.",
        )

    hashed_password = hash_password(request.password)
    new_user = UserModel(
        name=request.name,
        email=request.email,
        password=hashed_password,
        bio=request.bio,
        location=request.location,
        job_title=request.job_title,
    )

    try:
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        log.success(f"User created | user_id={new_user.id}")
        return {
            "status": "success",
            "message": "User created successfully",
            "user_details": _user_context(new_user),
        }
    except IntegrityError:
        db.rollback()
        log.error("IntegrityError during sign-up — rolled back")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Error while creating user",
        )


@router.post("/login")
def login(request: UserLoginRequest, req: Request, db: Session = Depends(get_db)):
    log = logger.bind(endpoint="login", ip=req.client.host, email=request.email)
    log.info("Login attempt")

    user = db.query(UserModel).filter(UserModel.email == request.email).first()
    if not user:
        log.warning("Login failed — user not found")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if not verify_password(request.password, user.password):
        log.warning(f"Login failed — incorrect password | user_id={user.id}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect password")

    access_token = create_access_token({"sub": str(user.id)})
    refresh_token = create_refresh_token(user.id, db)
    log.success(f"Login successful | user_id={user.id}")

    return {
        "status": "success",
        "message": "User logged in successfully",
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user_details": _user_context(user),
    }


@router.post("/refresh-token")
def refresh_token(request: RefreshTokenRequest, req: Request, db: Session = Depends(get_db)):
    """
    Exchange a valid refresh token for a new access token + rotated refresh token.
    Rotation: old token is revoked, a fresh one is issued (prevents replay attacks).
    """
    log = logger.bind(endpoint="refresh_token", ip=req.client.host)

    invalid_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # Find all non-revoked tokens and verify against hash
    candidates = (
        db.query(RefreshTokenModel)
        .filter(RefreshTokenModel.revoked == False)  # noqa: E712
        .all()
    )
    matched: RefreshTokenModel | None = None
    for candidate in candidates:
        if verify_password(request.refresh_token, candidate.token_hash):
            matched = candidate
            break

    if not matched:
        log.warning("Refresh token not found or already revoked")
        raise invalid_exc

    if matched.expires_at.replace(tzinfo=timezone.utc) < _utcnow():
        matched.revoked = True
        db.commit()
        log.warning(f"Expired refresh token used | user_id={matched.user_id} | token_id={matched.id}")
        raise invalid_exc

    user = db.query(UserModel).filter(UserModel.id == matched.user_id).first()
    if not user:
        log.error(f"Refresh token references non-existent user | user_id={matched.user_id}")
        raise invalid_exc

    # Rotate: revoke old, issue new
    matched.revoked = True
    db.commit()

    new_access = create_access_token({"sub": str(user.id)})
    new_refresh = create_refresh_token(user.id, db)
    log.success(f"Token refreshed | user_id={user.id} | old_token_id={matched.id}")

    return {
        "status": "success",
        "message": "Token refreshed successfully",
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "user_details": _user_context(user),
    }


@router.post("/logout")
def logout(
    request: RefreshTokenRequest,
    req: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Revokes the supplied refresh token.
    The short-lived access token naturally expires; no server-side blacklist needed.
    """
    log = logger.bind(endpoint="logout", ip=req.client.host, user_id=current_user.id)

    candidates = (
        db.query(RefreshTokenModel)
        .filter(
            RefreshTokenModel.user_id == current_user.id,
            RefreshTokenModel.revoked == False,  # noqa: E712
        )
        .all()
    )
    revoked = False
    for candidate in candidates:
        if verify_password(request.refresh_token, candidate.token_hash):
            candidate.revoked = True
            db.commit()
            revoked = True
            log.success(f"Refresh token revoked | token_id={candidate.id}")
            break

    if not revoked:
        log.warning("Logout called with unrecognised or already-revoked refresh token")

    # Always return success to avoid leaking token validity
    return {
        "status": "success",
        "message": "Logged out successfully",
        "user_details": _user_context(current_user),
    }


@router.post("/logout-all")
def logout_all(
    req: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Revokes ALL refresh tokens for the user — useful for 'sign out of all devices'."""
    log = logger.bind(endpoint="logout_all", ip=req.client.host, user_id=current_user.id)

    count = (
        db.query(RefreshTokenModel)
        .filter(
            RefreshTokenModel.user_id == current_user.id,
            RefreshTokenModel.revoked == False,  # noqa: E712
        )
        .update({"revoked": True})
    )
    db.commit()
    log.success(f"All sessions revoked | user_id={current_user.id} | count={count}")

    return {
        "status": "success",
        "message": f"Logged out of {count} session(s) successfully",
        "user_details": _user_context(current_user),
    }


@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, req: Request, db: Session = Depends(get_db)):
    """
    Generates a short-lived reset token.
    Always returns 200 regardless of whether the email exists (prevents user enumeration).
    In production wire this up to an email service (e.g. SendGrid / SES).
    """
    log = logger.bind(endpoint="forgot_password", ip=req.client.host, email=request.email)
    log.info("Password reset requested")

    user = db.query(UserModel).filter(UserModel.email == request.email).first()
    if user:
        # Invalidate any prior unused tokens for this user
        db.query(PasswordResetTokenModel).filter(
            PasswordResetTokenModel.user_id == user.id,
            PasswordResetTokenModel.used == False,  # noqa: E712
        ).update({"used": True})

        raw_token = secrets.token_urlsafe(48)
        hashed = hash_password(raw_token)
        record = PasswordResetTokenModel(
            user_id=user.id,
            token_hash=hashed,
            expires_at=_utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES),
            used=False,
        )
        db.add(record)
        db.commit()

        # TODO: send `raw_token` via email instead of logging it
        log.info(f"Reset token generated | user_id={user.id}")
        logger.debug(f"[DEV ONLY] reset token={raw_token}")  # remove in production
    else:
        log.warning("Password reset for unknown email — silently ignored")

    return {
        "status": "success",
        "message": "If that email is registered, a reset link has been sent.",
        "user_details": None,
    }


@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, req: Request, db: Session = Depends(get_db)):
    log = logger.bind(endpoint="reset_password", ip=req.client.host)
    log.info("Password reset submission")

    invalid_exc = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid or expired reset token",
    )

    candidates = (
        db.query(PasswordResetTokenModel)
        .filter(PasswordResetTokenModel.used == False)  # noqa: E712
        .all()
    )
    matched: PasswordResetTokenModel | None = None
    for candidate in candidates:
        if verify_password(request.token, candidate.token_hash):
            matched = candidate
            break

    if not matched:
        log.warning("Reset token not found or already used")
        raise invalid_exc

    if matched.expires_at.replace(tzinfo=timezone.utc) < _utcnow():
        matched.used = True
        db.commit()
        log.warning(f"Expired reset token used | user_id={matched.user_id}")
        raise invalid_exc

    user = db.query(UserModel).filter(UserModel.id == matched.user_id).first()
    if not user:
        log.error(f"Reset token references non-existent user | user_id={matched.user_id}")
        raise invalid_exc

    user.password = hash_password(request.new_password)
    matched.used = True

    # Revoke all refresh tokens on password reset (security best practice)
    db.query(RefreshTokenModel).filter(
        RefreshTokenModel.user_id == user.id,
        RefreshTokenModel.revoked == False,  # noqa: E712
    ).update({"revoked": True})

    db.commit()
    log.success(f"Password reset successful | user_id={user.id}")

    return {
        "status": "success",
        "message": "Password reset successfully. Please log in again.",
        "user_details": _user_context(user),
    }


@router.put("/change-password")
def change_password(
    request: ChangePasswordRequest,
    req: Request,
    current_user: UserModel = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    log = logger.bind(endpoint="change_password", ip=req.client.host, user_id=current_user.id)
    log.info("Password change attempt")

    if not verify_password(request.current_password, current_user.password):
        log.warning(f"Password change failed — wrong current password | user_id={current_user.id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )

    current_user.password = hash_password(request.new_password)

    # Revoke all OTHER refresh tokens so other devices are signed out
    db.query(RefreshTokenModel).filter(
        RefreshTokenModel.user_id == current_user.id,
        RefreshTokenModel.revoked == False,  # noqa: E712
    ).update({"revoked": True})

    db.commit()
    log.success(f"Password changed | user_id={current_user.id}")

    return {
        "status": "success",
        "message": "Password changed successfully. Please log in again.",
        "user_details": _user_context(current_user),
    }


@router.get("/check-token")
def check_token(req: Request, current_user: UserModel = Depends(get_current_user)):
    logger.bind(endpoint="check_token", ip=req.client.host, user_id=current_user.id).debug(
        "Token validation check"
    )
    return {
        "status": "success",
        "message": "Token is valid",
        "user_details": _user_context(current_user),
    }