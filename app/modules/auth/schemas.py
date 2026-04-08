from datetime import datetime
import re
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator

from .models import AuthProvider, ContactType, UserRole


# =========================
# TOKENS
# =========================


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# =========================
# GOOGLE AUTH
# =========================


class GoogleLoginRequest(BaseModel):
    id_token: str  # Frontenddan keladigan Google ID token


# =========================
# TELEGRAM AUTH
# =========================


class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


# =========================
# PHONE OTP AUTH
# =========================


class SendOtpRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+998\d{9}$")


class VerifyOtpRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+998\d{9}$")
    code: str = Field(..., min_length=4, max_length=6)


class PhoneAuthResponse(BaseModel):
    """
    Agar user mavjud bo‘lsa → token qaytadi
    Agar mavjud bo‘lmasa → need_registration
    """

    status: str  # "success" | "need_registration"
    token: Optional[Token] = None
    message: Optional[str] = None


# =========================
# USER RESPONSE
# =========================


class ContactResponse(BaseModel):
    id: int
    contact_type: ContactType
    value: str
    is_verified: bool
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)


class IdentityResponse(BaseModel):
    id: int
    provider: AuthProvider
    provider_id: str

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    is_active: bool
    global_role: UserRole
    created_at: datetime

    contacts: List[ContactResponse] = []
    identities: List[IdentityResponse] = []

    model_config = ConfigDict(from_attributes=True)


# =========================
# SESSION RESPONSE
# =========================


class SessionResponse(BaseModel):
    id: UUID
    user_agent: Optional[str]
    ip_address: Optional[str]
    expires_at: datetime
    is_revoked: bool

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# SEND OTP
# =====================================================


class SendCodeRequest(BaseModel):
    phone: str = Field(..., example="+998901234567")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()

        # Simple E.164 format check
        if not re.fullmatch(r"\+\d{9,15}", v):
            raise ValueError("Telefon raqam noto‘g‘ri formatda")

        return v


# =====================================================
# PHONE LOGIN
# =====================================================


class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., example="+998901234567")
    code: str = Field(..., min_length=4, max_length=6, example="1234")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        v = v.strip()

        if not re.fullmatch(r"\+\d{9,15}", v):
            raise ValueError("Telefon raqam noto‘g‘ri formatda")

        return v

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        if not v.isdigit():
            raise ValueError("Kod faqat raqamlardan iborat bo‘lishi kerak")
        return v

class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None