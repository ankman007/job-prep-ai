from sqlalchemy import Integer, Column, String, ForeignKey, JSON, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.db.session import Base


def _utcnow():
    return datetime.now(timezone.utc)


class UserModel(Base):
    __tablename__ = "users"

    id        = Column(Integer, primary_key=True, index=True)
    name      = Column(String, index=True, nullable=False)
    email     = Column(String, unique=True, index=True, nullable=False)
    password  = Column(String, nullable=False)
    bio       = Column(String, nullable=True)
    location  = Column(String, nullable=True)
    job_title = Column(String, nullable=True)

    # ── existing ──────────────────────────────────────────────────────────────
    cheat_sheets = relationship(
        "InterviewCheatSheetModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    # ── new (auth) ────────────────────────────────────────────────────────────
    refresh_tokens = relationship(
        "RefreshTokenModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    password_reset_tokens = relationship(
        "PasswordResetTokenModel",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class InterviewCheatSheetModel(Base):
    __tablename__ = "cheatsheets"

    id               = Column(Integer, primary_key=True, index=True)
    resume_text      = Column(String, nullable=True)
    job_description  = Column(String)
    generated_at     = Column(DateTime(timezone=True), default=_utcnow)
    content          = Column(JSON)
    cheatsheet_type  = Column(String)
    filename         = Column(String, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"))
    user    = relationship("UserModel", back_populates="cheat_sheets")


class RefreshTokenModel(Base):
    __tablename__ = "refresh_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String, nullable=False)
    revoked    = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user    = relationship("UserModel", back_populates="refresh_tokens")


class PasswordResetTokenModel(Base):
    __tablename__ = "password_reset_tokens"

    id         = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String, nullable=False)
    used       = Column(Boolean, default=False, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_utcnow)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user    = relationship("UserModel", back_populates="password_reset_tokens")