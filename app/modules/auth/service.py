import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import anyio
from fastapi import HTTPException, Request, status
from google.auth.transport import requests
from google.oauth2 import id_token
from sqlalchemy import select, delete, false
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import create_access_token

from app.modules.auth.models import (
    AuthCode,
    AuthProvider,
    ContactType,
    User,
    UserContact,
    UserIdentity,
    UserProfile,
    UserRole,
    UserSession,
    VerificationChannel,
    VerificationCode,
    VerificationPurpose,
)
from app.modules.auth.schemas import (
    AuthLoginResponse,
    GoogleLoginRequest,
    PhoneAuthResponse,
    TelegramLoginRequest,
    Token,
)
from app.modules.auth.sms import SmsService


logger = logging.getLogger(__name__)


class AuthService:
    OTP_EXPIRE_MINUTES = 5
    OTP_RESEND_COOLDOWN_SECONDS = 60
    OTP_MAX_ATTEMPTS = 5
    AUTH_CODE_EXPIRE_SECONDS = 120

    ROLE_DASHBOARD_URLS = {
        UserRole.ADMIN: "https://admin.enwis.uz",
        UserRole.TEACHER: "https://edu.enwis.uz",
        UserRole.USER: "https://app.enwis.uz",
    }

    SSO_CLIENTS = {
        "app": {
            "redirect_uris": [
                "https://app.enwis.uz/auth/callback",
            ],
        },
        "admin": {
            "redirect_uris": [
                "https://admin.enwis.uz/auth/callback",
            ],
        },
        "edu": {
            "redirect_uris": [
                "https://edu.enwis.uz/auth/callback",
            ],
        },
        "cefr": {
            "redirect_uris": [
                "https://cefr.enwis.uz/auth/callback",
            ],
        },
        "ielts": {
            "redirect_uris": [
                "https://ielts.enwis.uz/auth/callback",
            ],
        },
        "dtm": {
            "redirect_uris": [
                "https://dtm.enwis.uz/auth/callback",
            ],
        },
    }

    def __init__(self, db: AsyncSession):
        self.db = db

    # =====================================================
    # HELPERS
    # =====================================================

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def _verify_hash(self, plain: str, hashed: str) -> bool:
        return hmac.compare_digest(self._hash(plain), hashed)

    def _normalize_phone(self, phone: str) -> str:
        return phone.strip().replace(" ", "")

    def _normalize_email(self, email: str) -> str:
        return email.strip().lower()

    def _get_request_ip(self, request: Optional[Request]) -> Optional[str]:
        if request and request.client and request.client.host:
            return request.client.host[:50]
        return None

    def _get_request_user_agent(self, request: Optional[Request]) -> Optional[str]:
        if not request:
            return None
        ua = request.headers.get("user-agent")
        return ua[:255] if ua else None

    def _get_device_name(self, request: Optional[Request]) -> Optional[str]:
        ua = self._get_request_user_agent(request)
        return ua[:100] if ua else None

    def _get_client_name_from_request(self, request: Optional[Request]) -> str:
        if not request:
            return "unknown"

        host = request.headers.get("host", "")
        if host.startswith("cefr."):
            return "cefr"
        if host.startswith("ielts."):
            return "ielts"
        if host.startswith("dtm."):
            return "dtm"
        if host.startswith("admin."):
            return "admin"
        if host.startswith("edu."):
            return "edu"
        if host.startswith("app."):
            return "app"
        if host.startswith("auth."):
            return "auth"
        return "unknown"

    def resolve_dashboard_url(self, user: User) -> str:
        return self.ROLE_DASHBOARD_URLS.get(user.global_role, "https://app.enwis.uz")

    async def _build_login_response(
        self, user: User, request: Request
    ) -> AuthLoginResponse:
        token = await self._create_session_and_tokens(user, request)
        return AuthLoginResponse(
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            token_type=token.token_type,
            redirect_to=self.resolve_dashboard_url(user),
        )

    def validate_client_redirect(self, client_id: str, redirect_uri: str) -> None:
        client = self.SSO_CLIENTS.get(client_id)
        if not client:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown client_id",
            )

        allowed_uris = client["redirect_uris"]
        if redirect_uri not in allowed_uris:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid redirect_uri",
            )

    async def _get_user_full(self, user_id: int) -> User:
        stmt = (
            select(User)
            .options(
                selectinload(User.profile),
                selectinload(User.contacts),
                selectinload(User.identities),
                selectinload(User.sessions),
                selectinload(User.subscriptions),
                selectinload(User.payments),
            )
            .where(User.id == user_id)
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return user

    async def _find_identity(
        self,
        provider: AuthProvider,
        provider_id: str,
    ) -> Optional[UserIdentity]:
        stmt = select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_id == provider_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_contact(
        self,
        contact_type: ContactType,
        normalized_value: str,
    ) -> Optional[UserContact]:
        stmt = select(UserContact).where(
            UserContact.contact_type == contact_type,
            UserContact.normalized_value == normalized_value,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _generate_user_id(self) -> int:
        for _ in range(10):
            candidate = secrets.randbelow(9_000_000_000) + 1_000_000_000
            stmt = select(User.id).where(User.id == candidate)
            exists = (await self.db.execute(stmt)).scalar_one_or_none()
            if not exists:
                return candidate

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not generate user id",
        )

    async def _generate_unique_username(self, base: str) -> str:
        cleaned = "".join(ch for ch in base.lower() if ch.isalnum() or ch == "_").strip(
            "_"
        )
        cleaned = cleaned or "user"
        cleaned = cleaned[:30]

        for idx in range(20):
            candidate = cleaned if idx == 0 else f"{cleaned}_{secrets.randbelow(9999)}"
            stmt = select(UserProfile.user_id).where(UserProfile.username == candidate)
            exists = (await self.db.execute(stmt)).scalar_one_or_none()
            if not exists:
                return candidate

        return f"user_{secrets.token_hex(4)}"

    # =====================================================
    # SESSION / TOKEN
    # =====================================================

    async def _create_session_and_tokens(
        self,
        user: User,
        request: Request,
        session_family_id: Optional[uuid.UUID] = None,
    ) -> Token:
        access_token = create_access_token(
            user_id=user.id,
            extra_data={"role": user.global_role.value},
        )

        refresh_token = secrets.token_urlsafe(64)
        refresh_token_hash = self._hash(refresh_token)
        now = self._now()

        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=refresh_token_hash,
            session_family_id=session_family_id or uuid.uuid4(),
            user_agent=self._get_request_user_agent(request),
            ip_address=self._get_request_ip(request),
            device_name=self._get_device_name(request),
            client_name=self._get_client_name_from_request(request),
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_DAYS),
            last_seen_at=now,
            is_revoked=False,
            revoked_at=None,
        )

        self.db.add(session)
        await self.db.flush()

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
        )

    async def refresh_tokens(self, refresh_token: str, request: Request) -> Token:
        now = self._now()
        refresh_hash = self._hash(refresh_token)

        async with self.db.begin():
            stmt = (
                select(UserSession)
                .where(UserSession.refresh_token_hash == refresh_hash)
                .with_for_update()
            )
            result = await self.db.execute(stmt)
            session = result.scalar_one_or_none()

            if not session:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid refresh token",
                )

            if session.is_revoked:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token revoked",
                )

            if session.expires_at <= now:
                session.is_revoked = True
                session.revoked_at = now
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token expired",
                )

            user = await self._get_user_full(session.user_id)

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User inactive",
                )

            new_tokens = await self._create_session_and_tokens(
                user=user,
                request=request,
                session_family_id=session.session_family_id,
            )

            stmt_new = select(UserSession).where(
                UserSession.refresh_token_hash == self._hash(new_tokens.refresh_token)
            )
            new_session = (await self.db.execute(stmt_new)).scalar_one()

            session.is_revoked = True
            session.revoked_at = now
            session.replaced_by_session_id = new_session.id
            session.last_seen_at = now

            return new_tokens

    async def get_active_sessions(self, user_id: int) -> list[UserSession]:
        stmt = (
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_revoked == false(),
            )
            .order_by(UserSession.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def revoke_session(self, user_id: int, session_id: uuid.UUID) -> None:
        async with self.db.begin():
            stmt = (
                select(UserSession)
                .where(
                    UserSession.id == session_id,
                    UserSession.user_id == user_id,
                )
                .with_for_update()
            )
            session = (await self.db.execute(stmt)).scalar_one_or_none()

            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Session not found",
                )

            if not session.is_revoked:
                session.is_revoked = True
                session.revoked_at = self._now()

    # =====================================================
    # SOCIAL AUTH CORE
    # =====================================================

    async def _social_auth(
        self,
        provider: AuthProvider,
        provider_id: str,
        request: Request,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        username: Optional[str] = None,
    ) -> User:
        normalized_email = self._normalize_email(email) if email else None

        async with self.db.begin():
            identity = await self._find_identity(
                provider=provider, provider_id=provider_id
            )

            if identity:
                user = await self._get_user_full(identity.user_id)

                if not user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User inactive",
                    )

                if user.profile:
                    if full_name:
                        user.profile.full_name = full_name
                    if avatar_url:
                        user.profile.avatar_url = avatar_url
                    if username and not user.profile.username:
                        user.profile.username = await self._generate_unique_username(
                            username
                        )

                if normalized_email:
                    existing_email = await self._find_contact(
                        contact_type=ContactType.EMAIL,
                        normalized_value=normalized_email,
                    )
                    if not existing_email:
                        self.db.add(
                            UserContact(
                                user_id=user.id,
                                contact_type=ContactType.EMAIL,
                                value=normalized_email,
                                normalized_value=normalized_email,
                                is_verified=True,
                                is_primary=False,
                            )
                        )

                return user

            existing_user = None
            if normalized_email:
                existing_email_contact = await self._find_contact(
                    contact_type=ContactType.EMAIL,
                    normalized_value=normalized_email,
                )
                if existing_email_contact:
                    existing_user = await self._get_user_full(
                        existing_email_contact.user_id
                    )

            if existing_user:
                if not existing_user.is_active:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="User inactive",
                    )

                self.db.add(
                    UserIdentity(
                        user_id=existing_user.id,
                        provider=provider,
                        provider_id=provider_id,
                    )
                )

                if existing_user.profile:
                    if full_name and not existing_user.profile.full_name:
                        existing_user.profile.full_name = full_name
                    if avatar_url and not existing_user.profile.avatar_url:
                        existing_user.profile.avatar_url = avatar_url
                    if username and not existing_user.profile.username:
                        existing_user.profile.username = (
                            await self._generate_unique_username(username)
                        )
                else:
                    self.db.add(
                        UserProfile(
                            user_id=existing_user.id,
                            full_name=full_name,
                            avatar_url=avatar_url,
                            username=await self._generate_unique_username(
                                username or "user"
                            ),
                        )
                    )

                return existing_user

            user_id = await self._generate_user_id()

            base_username = username
            if not base_username and normalized_email:
                base_username = normalized_email.split("@")[0]
            if not base_username:
                base_username = "user"

            final_username = await self._generate_unique_username(base_username)

            user = User(
                id=user_id,
                is_active=True,
                global_role=UserRole.USER,
            )
            self.db.add(user)
            await self.db.flush()

            self.db.add(
                UserProfile(
                    user_id=user.id,
                    full_name=full_name,
                    avatar_url=avatar_url,
                    username=final_username,
                )
            )

            self.db.add(
                UserIdentity(
                    user_id=user.id,
                    provider=provider,
                    provider_id=provider_id,
                )
            )

            if normalized_email:
                self.db.add(
                    UserContact(
                        user_id=user.id,
                        contact_type=ContactType.EMAIL,
                        value=normalized_email,
                        normalized_value=normalized_email,
                        is_verified=True,
                        is_primary=True,
                    )
                )

            try:
                await self.db.flush()
            except IntegrityError as e:
                logger.exception("Integrity error during social auth create")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not create social account",
                ) from e

            return user

    async def social_login_response(
        self,
        provider: AuthProvider,
        provider_id: str,
        request: Request,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        username: Optional[str] = None,
    ) -> AuthLoginResponse:
        user = await self._social_auth(
            provider=provider,
            provider_id=provider_id,
            request=request,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            username=username,
        )
        return await self._build_login_response(user, request)

    # =====================================================
    # GOOGLE
    # =====================================================

    async def verify_google_token(self, token: str) -> dict:
        try:
            payload = id_token.verify_oauth2_token(
                token,
                requests.Request(),
                settings.GOOGLE_CLIENT_ID,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google token invalid",
            ) from e

        if payload.get("iss") not in {
            "accounts.google.com",
            "https://accounts.google.com",
        }:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Google issuer",
            )

        return payload

    async def google_login(
        self, data: GoogleLoginRequest, request: Request
    ) -> AuthLoginResponse:
        g_data = await self.verify_google_token(data.id_token)

        return await self.social_login_response(
            provider=AuthProvider.GOOGLE,
            provider_id=g_data["sub"],
            email=g_data.get("email"),
            full_name=g_data.get("name"),
            avatar_url=g_data.get("picture"),
            username=g_data.get("email", "").split("@")[0]
            if g_data.get("email")
            else None,
            request=request,
        )

    # =====================================================
    # TELEGRAM
    # =====================================================

    def _verify_telegram_hash(self, data: TelegramLoginRequest) -> bool:
        data_dict = data.model_dump(exclude={"hash"})
        check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data_dict.items()) if v is not None
        )
        secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
        calculated_hash = hmac.new(
            secret_key,
            check_string.encode(),
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(calculated_hash, data.hash)

    async def telegram_login(
        self, data: TelegramLoginRequest, request: Request
    ) -> AuthLoginResponse:
        if not self._verify_telegram_hash(data):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Telegram authentication failed",
            )

        full_name = f"{data.first_name or ''} {data.last_name or ''}".strip()

        return await self.social_login_response(
            provider=AuthProvider.TELEGRAM,
            provider_id=str(data.id),
            username=data.username,
            full_name=full_name or None,
            avatar_url=data.photo_url,
            request=request,
        )

    # =====================================================
    # OTP
    # =====================================================

    async def send_otp(
        self,
        phone: str,
        request: Optional[Request] = None,
        source: str = "web",
        purpose: VerificationPurpose = VerificationPurpose.LOGIN,
        channel: VerificationChannel = VerificationChannel.SMS,
    ) -> dict:
        now = self._now()
        normalized_phone = self._normalize_phone(phone)

        stmt = select(VerificationCode).where(
            VerificationCode.normalized_target == normalized_phone,
            VerificationCode.purpose == purpose,
            VerificationCode.created_at
            > now - timedelta(seconds=self.OTP_RESEND_COOLDOWN_SECONDS),
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests",
            )

        code = str(secrets.randbelow(900000) + 100000)
        message = f"Enwis tasdiqlash kodingiz: {code}"

        async with self.db.begin():
            await self.db.execute(
                delete(VerificationCode).where(
                    VerificationCode.normalized_target == normalized_phone,
                    VerificationCode.purpose == purpose,
                    VerificationCode.is_used == false(),
                )
            )

            record = VerificationCode(
                target=normalized_phone,
                normalized_target=normalized_phone,
                purpose=purpose,
                channel=channel,
                code_hash=self._hash(code),
                failed_attempts=0,
                max_attempts=self.OTP_MAX_ATTEMPTS,
                expires_at=now + timedelta(minutes=self.OTP_EXPIRE_MINUTES),
                is_used=False,
                used_at=None,
                sent_to_ip=self._get_request_ip(request),
                sent_user_agent=self._get_request_user_agent(request),
            )
            self.db.add(record)

        if source == "bot":
            return {"status": "sent", "code": code}

        await anyio.to_thread.run_sync(
            SmsService.send_sms,
            normalized_phone,
            message,
        )

        if settings.ENV.lower() == "production":
            return {"status": "sent"}

        return {"status": "sent", "code": code, "message": message}

    async def _verify_otp(
        self,
        phone: str,
        code: str,
        purpose: VerificationPurpose = VerificationPurpose.LOGIN,
    ) -> bool:
        now = self._now()
        normalized_phone = self._normalize_phone(phone)

        stmt = (
            select(VerificationCode)
            .where(
                VerificationCode.normalized_target == normalized_phone,
                VerificationCode.purpose == purpose,
                VerificationCode.is_used == false(),
                VerificationCode.expires_at > now,
            )
            .order_by(VerificationCode.created_at.desc())
            .with_for_update()
        )

        record = (await self.db.execute(stmt)).scalars().first()

        if not record:
            return False

        if record.failed_attempts >= record.max_attempts:
            return False

        if not self._verify_hash(code, record.code_hash):
            record.failed_attempts += 1
            return False

        record.is_used = True
        record.used_at = now
        return True

    # =====================================================
    # PHONE AUTH
    # =====================================================

    async def authenticate_by_phone(
        self,
        phone: str,
        code: str,
        request: Request,
    ) -> PhoneAuthResponse:
        normalized_phone = self._normalize_phone(phone)

        async with self.db.begin():
            is_valid = await self._verify_otp(
                phone=normalized_phone,
                code=code,
                purpose=VerificationPurpose.LOGIN,
            )

            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Kod noto‘g‘ri yoki eskirgan",
                )

            contact = await self._find_contact(
                contact_type=ContactType.PHONE,
                normalized_value=normalized_phone,
            )

            if not contact:
                return PhoneAuthResponse(
                    status="need_registration",
                    message="Telefon raqam tasdiqlandi, lekin akkaunt topilmadi",
                )

            user = await self._get_user_full(contact.user_id)

            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User inactive",
                )

            if not contact.is_verified:
                contact.is_verified = True

            token = await self._create_session_and_tokens(user, request)

            return PhoneAuthResponse(
                status="success",
                token=token,
                redirect_to=self.resolve_dashboard_url(user),
                message="Muvaffaqiyatli tizimga kirildi",
            )

    async def register_by_phone(
        self,
        phone: str,
        full_name: Optional[str],
        request: Request,
    ) -> AuthLoginResponse:
        normalized_phone = self._normalize_phone(phone)

        async with self.db.begin():
            existing_contact = await self._find_contact(
                contact_type=ContactType.PHONE,
                normalized_value=normalized_phone,
            )
            if existing_contact:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Phone already registered",
                )

            user_id = await self._generate_user_id()
            username = await self._generate_unique_username(
                f"user_{normalized_phone[-4:]}"
            )

            user = User(
                id=user_id,
                is_active=True,
                global_role=UserRole.USER,
            )
            self.db.add(user)
            await self.db.flush()

            self.db.add(
                UserProfile(
                    user_id=user.id,
                    full_name=full_name,
                    username=username,
                )
            )

            self.db.add(
                UserContact(
                    user_id=user.id,
                    contact_type=ContactType.PHONE,
                    value=normalized_phone,
                    normalized_value=normalized_phone,
                    is_verified=True,
                    is_primary=True,
                )
            )

            self.db.add(
                UserIdentity(
                    user_id=user.id,
                    provider=AuthProvider.PHONE,
                    provider_id=normalized_phone,
                )
            )

            return await self._build_login_response(user, request)

    # =====================================================
    # AUTH CODE / SSO
    # =====================================================

    async def create_auth_code(
        self,
        user: User,
        client_name: str,
        redirect_uri: str,
    ) -> str:
        self.validate_client_redirect(client_name, redirect_uri)

        raw_code = secrets.token_urlsafe(48)
        code_hash = self._hash(raw_code)
        now = self._now()

        async with self.db.begin():
            auth_code = AuthCode(
                user_id=user.id,
                client_name=client_name,
                redirect_uri=redirect_uri,
                code_hash=code_hash,
                expires_at=now + timedelta(seconds=self.AUTH_CODE_EXPIRE_SECONDS),
                is_used=False,
                used_at=None,
            )
            self.db.add(auth_code)

        return raw_code

    async def exchange_auth_code(
        self,
        code: str,
        client_name: str,
        redirect_uri: str,
        request: Request,
    ) -> Token:
        self.validate_client_redirect(client_name, redirect_uri)

        now = self._now()
        code_hash = self._hash(code)

        async with self.db.begin():
            stmt = (
                select(AuthCode)
                .where(AuthCode.code_hash == code_hash)
                .with_for_update()
            )
            auth_code = (await self.db.execute(stmt)).scalar_one_or_none()

            if not auth_code:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid auth code",
                )

            if auth_code.is_used:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Auth code already used",
                )

            if auth_code.expires_at <= now:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Auth code expired",
                )

            if auth_code.client_name != client_name:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Client mismatch",
                )

            if auth_code.redirect_uri != redirect_uri:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Redirect URI mismatch",
                )

            auth_code.is_used = True
            auth_code.used_at = now

            user = await self._get_user_full(auth_code.user_id)
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User inactive",
                )

            return await self._create_session_and_tokens(user, request)

    # =====================================================
    # LOGOUT
    # =====================================================

    async def logout_by_refresh_token(self, refresh_token: str) -> None:
        refresh_hash = self._hash(refresh_token)
        now = self._now()

        async with self.db.begin():
            stmt = (
                select(UserSession)
                .where(UserSession.refresh_token_hash == refresh_hash)
                .with_for_update()
            )
            session = (await self.db.execute(stmt)).scalar_one_or_none()

            if not session:
                return

            if not session.is_revoked:
                session.is_revoked = True
                session.revoked_at = now

    async def logout(self, user_id: int, request: Request) -> None:
        now = self._now()
        ip = self._get_request_ip(request)
        ua = self._get_request_user_agent(request)

        async with self.db.begin():
            stmt = select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.is_revoked == false(),
                UserSession.ip_address == ip,
                UserSession.user_agent == ua,
            )
            sessions = (await self.db.execute(stmt)).scalars().all()

            for session in sessions:
                session.is_revoked = True
                session.revoked_at = now

    async def logout_all(self, user_id: int) -> None:
        now = self._now()

        async with self.db.begin():
            stmt = select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.is_revoked == false(),
            )
            sessions = (await self.db.execute(stmt)).scalars().all()

            for session in sessions:
                session.is_revoked = True
                session.revoked_at = now
