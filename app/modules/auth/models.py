import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# =========================
# Mixins
# =========================

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# =========================
# Enums
# =========================

class AuthProvider(str, PyEnum):
    GOOGLE = "google"
    TELEGRAM = "telegram"


class ContactType(str, PyEnum):
    EMAIL = "email"
    PHONE = "phone"
    TELEGRAM = "telegram"


class UserRole(str, PyEnum):
    USER = "user"
    ADMIN = "admin"
    TEACHER = "teacher"


# =========================
# Models
# =========================

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=False,  # ❗ safe default
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    global_role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False),  # SQLite safe
        default=UserRole.USER,
        nullable=False,
    )

    # 🔑 Session family (refresh rotation)
    session_family_id: Mapped[str] = mapped_column(
        String(36),
        default=lambda: str(uuid.uuid4()),
        index=True,
        nullable=False,
    )

    # 🔁 Token rotation chain
    replaced_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    # Relationships
    profile: Mapped[Optional["UserProfile"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False,
    )

    identities: Mapped[List["UserIdentity"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    contacts: Mapped[List["UserContact"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    sessions: Mapped[List["UserSession"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )


# =========================
# Profile
# =========================

class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    username: Mapped[Optional[str]] = mapped_column(
        String(50), unique=True
    )
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    bio: Mapped[Optional[str]] = mapped_column(Text)
    birth_date: Mapped[Optional[datetime]] = mapped_column(Date)
    language: Mapped[Optional[str]] = mapped_column(String(10))
    timezone: Mapped[Optional[str]] = mapped_column(String(50))

    user: Mapped["User"] = relationship(back_populates="profile")


# =========================
# Social Identity
# =========================

class UserIdentity(Base, TimestampMixin):
    __tablename__ = "user_identities"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    provider: Mapped[AuthProvider] = mapped_column(
        Enum(AuthProvider, native_enum=False),
        nullable=False,
    )

    provider_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "provider",
            "provider_id",
            name="uq_provider_provider_id",
        ),
    )

    user: Mapped["User"] = relationship(back_populates="identities")


# =========================
# Contacts
# =========================

class UserContact(Base, TimestampMixin):
    __tablename__ = "user_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    contact_type: Mapped[ContactType] = mapped_column(
        Enum(ContactType, native_enum=False),
        nullable=False,
    )

    value: Mapped[str] = mapped_column(String(255), nullable=False)

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "contact_type",
            "value",
            name="uq_contact_type_value",
        ),
        Index("idx_user_contacts_user_id", "user_id"),
    )

    user: Mapped["User"] = relationship(back_populates="contacts")


# =========================
# Sessions (CRITICAL)
# =========================

class UserSession(Base, TimestampMixin):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    refresh_token_hash: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    family_id: Mapped[str] = mapped_column(
        String(36),
        index=True,
    )

    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    __table_args__ = (
        Index("idx_user_active_sessions", "user_id", "is_revoked"),
    )

    user: Mapped["User"] = relationship(back_populates="sessions")


# =========================
# Verification Codes
# =========================

class VerificationCode(Base, TimestampMixin):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True)

    target: Mapped[str] = mapped_column(String(255), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))

    failed_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    is_used: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    __table_args__ = (
        Index("idx_active_code", "target", "is_used"),
    )