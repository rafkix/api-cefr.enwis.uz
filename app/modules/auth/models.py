import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer,
    String, Text, UniqueConstraint, func, Index)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Base ni markaziy joydan olamiz
from app.core.database import Base

class TimestampMixin:
    """Barcha jadvallarga created_at va updated_at qo'shish uchun mixin."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now()
    )

class AuthProvider(str, PyEnum):
    LOCAL = "local"
    GOOGLE = "google"
    TELEGRAM = "telegram"
    ONE_ID = "one_id"

class UserRole(str, PyEnum):
    USER = "user"
    ADMIN = "admin"
    DEVELOPER = "developer"

class VerificationPurpose(str, PyEnum):
    REGISTER = "register"
    RESET_PASSWORD = "reset_password"
    VERIFY_EMAIL = "verify_email"
    VERIFY_PHONE = "verify_phone"
    LOGIN = "login"
    ADD_CONTACT = "add_contact"

class User(Base, TimestampMixin):
    """
    Foydalanuvchining asosiy modeli.
    """
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True, autoincrement=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    global_role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)

    # FAQAT BIR MARTA VA TO'LIQ YO'L BILAN YOZAMIZ:
    profile: Mapped["UserProfile"] = relationship(
        "app.modules.auth.models.UserProfile", 
        back_populates="user", 
        uselist=False, 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )
    identities: Mapped[List["UserIdentity"]] = relationship(
        "app.modules.auth.models.UserIdentity", 
        back_populates="user", 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )
    contacts: Mapped[List["UserContact"]] = relationship(
        "app.modules.auth.models.UserContact", 
        back_populates="user", 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )
    sessions: Mapped[List["UserSession"]] = relationship(
        "app.modules.auth.models.UserSession", 
        back_populates="user", 
        cascade="all, delete-orphan"
    )

    @property
    def email(self) -> Optional[str]:
        return next((c.value for c in self.contacts if c.contact_type == "email" and c.is_primary), None)

    @property
    def phone(self) -> Optional[str]:
        return next((c.value for c in self.contacts if c.contact_type == "phone" and c.is_primary), None)


class UserProfile(Base, TimestampMixin):
    """Foydalanuvchining shaxsiy ma'lumotlari."""
    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    
    full_name: Mapped[str] = mapped_column(String(255))
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    birth_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    
    user: Mapped["User"] = relationship("User", back_populates="profile")


class UserIdentity(Base, TimestampMixin):
    """Auth provayderlar (Local, Google, Telegram) bilan bog'lanish."""
    __tablename__ = "user_identities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    
    provider: Mapped[AuthProvider] = mapped_column(Enum(AuthProvider))
    provider_id: Mapped[str] = mapped_column(String, index=True) # Email yoki Social ID
    password_hash: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    
    # Bitta provayderda bitta ID faqat bir marta bo'lishi shart
    __table_args__ = (UniqueConstraint("provider", "provider_id", name="_provider_id_uc"),)

    user: Mapped["User"] = relationship("User", back_populates="identities")


class UserContact(Base, TimestampMixin):
    """Foydalanuvchining aloqa vositalari."""
    __tablename__ = "user_contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    
    contact_type: Mapped[str] = mapped_column(String(20)) # email, phone, telegram
    value: Mapped[str] = mapped_column(String(255), index=True)
    
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="contacts")


class UserSession(Base, TimestampMixin):
    """
    Refresh Token sessiyalari. 
    Domain-locking va Xavfsizlik uchun ishlatiladi.
    """
    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    
    # SHA256 bilan xeshlanadi
    refresh_token_hash: Mapped[str] = mapped_column(String, index=True)
    
    user_agent: Mapped[Optional[str]] = mapped_column(String)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    
    # Refresh token amal qilish muddati
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship("User", back_populates="sessions")


class VerificationCode(Base, TimestampMixin):
    """SMS yoki Email kodlarni tasdiqlash uchun."""
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    
    target: Mapped[str] = mapped_column(String, index=True) # email/phone
    code: Mapped[str] = mapped_column(String(10))
    purpose: Mapped[VerificationPurpose] = mapped_column(Enum(VerificationPurpose))
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)

    # Tezkor qidirish uchun kompozit indeks
    __table_args__ = (Index("idx_target_code_active", "target", "code", "is_used"),)