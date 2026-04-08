from datetime import date, datetime
from decimal import Decimal
import re
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .models import (
    AuthProvider,
    ContactType,
    PaymentProvider,
    PaymentStatus,
    PlanInterval,
    ProductCode,
    SubscriptionStatus,
    UserRole,
    VerificationChannel,
    VerificationPurpose,
)


# =====================================================
# Helpers
# =====================================================

UZ_PHONE_REGEX = re.compile(r"^\+998\d{9}$")


def normalize_uz_phone(value: str) -> str:
    value = value.strip().replace(" ", "")
    if not UZ_PHONE_REGEX.fullmatch(value):
        raise ValueError("Telefon raqam noto‘g‘ri formatda. Masalan: +998901234567")
    return value


# =====================================================
# TOKENS / AUTH
# =====================================================


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthLoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    redirect_to: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class LogoutByTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10)


class GoogleLoginRequest(BaseModel):
    id_token: str = Field(..., min_length=20)


class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


# =====================================================
# OTP / VERIFICATION
# =====================================================


class SendCodeRequest(BaseModel):
    phone: str = Field(..., examples=["+998901234567"])
    purpose: VerificationPurpose = VerificationPurpose.LOGIN
    channel: VerificationChannel = VerificationChannel.SMS

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_uz_phone(v)


class VerifyCodeRequest(BaseModel):
    phone: str = Field(..., examples=["+998901234567"])
    code: str = Field(..., min_length=4, max_length=6, examples=["123456"])
    purpose: VerificationPurpose = VerificationPurpose.LOGIN

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_uz_phone(v)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        value = v.strip()
        if not value.isdigit():
            raise ValueError("Kod faqat raqamlardan iborat bo‘lishi kerak")
        return value


class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., examples=["+998901234567"])
    code: str = Field(..., min_length=4, max_length=6, examples=["123456"])

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_uz_phone(v)

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        value = v.strip()
        if not value.isdigit():
            raise ValueError("Kod faqat raqamlardan iborat bo‘lishi kerak")
        return value


class PhoneRegisterRequest(BaseModel):
    phone: str = Field(..., examples=["+998901234567"])
    full_name: Optional[str] = Field(default=None, max_length=255)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return normalize_uz_phone(v)


class PhoneAuthResponse(BaseModel):
    status: Literal["success", "need_registration"]
    token: Optional[Token] = None
    redirect_to: Optional[str] = None
    message: Optional[str] = None


class VerificationCodeResponse(BaseModel):
    id: int
    target: str
    normalized_target: str
    purpose: VerificationPurpose
    channel: VerificationChannel
    failed_attempts: int
    max_attempts: int
    expires_at: datetime
    is_used: bool
    used_at: Optional[datetime] = None
    sent_to_ip: Optional[str] = None
    sent_user_agent: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# USER / PROFILE / CONTACT / IDENTITY
# =====================================================


class UserProfileResponse(BaseModel):
    full_name: Optional[str] = None
    username: Optional[str] = None
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserIdentityResponse(BaseModel):
    id: int
    provider: AuthProvider
    provider_id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserContactResponse(BaseModel):
    id: int
    contact_type: ContactType
    value: str
    normalized_value: str
    is_verified: bool
    is_primary: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: int
    is_active: bool
    global_role: UserRole
    created_at: datetime
    updated_at: datetime

    profile: Optional[UserProfileResponse] = None
    contacts: List[UserContactResponse] = Field(default_factory=list)
    identities: List[UserIdentityResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class UserWithRelationsResponse(UserResponse):
    sessions: List["SessionResponse"] = Field(default_factory=list)
    subscriptions: List["SubscriptionResponse"] = Field(default_factory=list)
    payments: List["PaymentResponse"] = Field(default_factory=list)


class CreateUserProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=50)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    language: Optional[str] = Field(default=None, max_length=10)
    timezone: Optional[str] = Field(default=None, max_length=50)


class UpdateUserProfileRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=50)
    avatar_url: Optional[str] = Field(default=None, max_length=500)
    bio: Optional[str] = None
    birth_date: Optional[date] = None
    language: Optional[str] = Field(default=None, max_length=10)
    timezone: Optional[str] = Field(default=None, max_length=50)


class CreateContactRequest(BaseModel):
    contact_type: ContactType
    value: str
    is_primary: bool = False

    @field_validator("value")
    @classmethod
    def validate_value(cls, v: str) -> str:
        value = v.strip()
        if not value:
            raise ValueError("Qiymat bo‘sh bo‘lishi mumkin emas")
        return value


class UpdateContactRequest(BaseModel):
    is_verified: Optional[bool] = None
    is_primary: Optional[bool] = None


# =====================================================
# SESSIONS
# =====================================================


class SessionResponse(BaseModel):
    id: UUID
    user_id: int
    session_family_id: UUID
    replaced_by_session_id: Optional[UUID] = None
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    device_name: Optional[str] = None
    client_name: Optional[str] = None
    expires_at: datetime
    last_seen_at: Optional[datetime] = None
    is_revoked: bool
    revoked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =====================================================
# ROLE / REDIRECT
# =====================================================


class DashboardRedirectResponse(BaseModel):
    role: UserRole
    redirect_to: str


# =====================================================
# PRODUCTS / PLANS
# =====================================================


class ProductResponse(BaseModel):
    id: int
    code: ProductCode
    name: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PlanResponse(BaseModel):
    id: int
    product_id: int
    code: str
    name: str
    price_amount: Decimal
    price_currency: str
    interval: PlanInterval
    interval_count: int
    is_trial: bool
    is_active: bool
    description: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductWithPlansResponse(ProductResponse):
    plans: List[PlanResponse] = Field(default_factory=list)


class CreateProductRequest(BaseModel):
    code: ProductCode
    name: str = Field(..., min_length=2, max_length=100)
    is_active: bool = True


class UpdateProductRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    is_active: Optional[bool] = None


class CreatePlanRequest(BaseModel):
    product_id: int
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    price_amount: Decimal = Field(..., ge=0)
    price_currency: str = Field(default="UZS", min_length=3, max_length=10)
    interval: PlanInterval
    interval_count: int = Field(default=1, ge=1)
    is_trial: bool = False
    is_active: bool = True
    description: Optional[str] = None


class UpdatePlanRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    price_amount: Optional[Decimal] = Field(default=None, ge=0)
    price_currency: Optional[str] = Field(default=None, min_length=3, max_length=10)
    interval: Optional[PlanInterval] = None
    interval_count: Optional[int] = Field(default=None, ge=1)
    is_trial: Optional[bool] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


# =====================================================
# SUBSCRIPTIONS
# =====================================================


class SubscriptionResponse(BaseModel):
    id: UUID
    user_id: int
    product_id: int
    plan_id: int
    status: SubscriptionStatus
    starts_at: datetime
    ends_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    auto_renew: bool
    source_payment_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SubscriptionDetailedResponse(SubscriptionResponse):
    product: ProductResponse
    plan: PlanResponse


class CreateSubscriptionRequest(BaseModel):
    user_id: int
    product_id: int
    plan_id: int
    starts_at: datetime
    ends_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    auto_renew: bool = False
    source_payment_id: Optional[UUID] = None


class UpdateSubscriptionRequest(BaseModel):
    status: Optional[SubscriptionStatus] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    canceled_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    auto_renew: Optional[bool] = None
    source_payment_id: Optional[UUID] = None


# =====================================================
# PAYMENTS
# =====================================================


class PaymentResponse(BaseModel):
    id: UUID
    user_id: int
    provider: PaymentProvider
    external_id: Optional[str] = None
    amount: Decimal
    currency: str
    status: PaymentStatus
    product_code: Optional[ProductCode] = None
    metadata_json: Optional[str] = None
    paid_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CreatePaymentRequest(BaseModel):
    user_id: int
    provider: PaymentProvider
    external_id: Optional[str] = Field(default=None, max_length=255)
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="UZS", min_length=3, max_length=10)
    product_code: Optional[ProductCode] = None
    metadata_json: Optional[str] = None


class UpdatePaymentRequest(BaseModel):
    external_id: Optional[str] = Field(default=None, max_length=255)
    status: Optional[PaymentStatus] = None
    paid_at: Optional[datetime] = None
    metadata_json: Optional[str] = None


# =====================================================
# AUTH CODE / SSO
# =====================================================


class AuthCodeResponse(BaseModel):
    id: UUID
    user_id: int
    client_name: str
    redirect_uri: str
    expires_at: datetime
    is_used: bool
    used_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuthorizeQuery(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=50)
    redirect_uri: str = Field(..., min_length=1, max_length=500)
    state: str = Field(..., min_length=8, max_length=500)


class ExchangeTokenRequest(BaseModel):
    code: str = Field(..., min_length=8)
    client_id: str = Field(..., min_length=1, max_length=50)
    redirect_uri: str = Field(..., min_length=1, max_length=500)


class ExchangeTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthorizeRedirectResponse(BaseModel):
    redirect_to: str


# =====================================================
# PRODUCT ACCESS / PORTAL
# =====================================================


class ProductAccessResponse(BaseModel):
    product_code: ProductCode
    has_access: bool
    subscription_status: Optional[SubscriptionStatus] = None
    redirect_to: Optional[str] = None


class PortalSummaryResponse(BaseModel):
    user: UserResponse
    subscriptions: List[SubscriptionDetailedResponse] = Field(default_factory=list)
    products: List[ProductWithPlansResponse] = Field(default_factory=list)


# =====================================================
# Generic status response
# =====================================================


class StatusResponse(BaseModel):
    status: str
    message: Optional[str] = None


# =====================================================
# Rebuild forward refs
# =====================================================

UserWithRelationsResponse.model_rebuild()
