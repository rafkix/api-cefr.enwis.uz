import secrets
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import anyio
from fastapi import HTTPException, Request
from sqlalchemy import select, delete, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token
from app.core.config import settings
from google.oauth2 import id_token
from google.auth.transport import requests

from app.modules.auth.schemas import (
    Token,
    GoogleLoginRequest,
    TelegramLoginRequest,
    PhoneAuthResponse,
)

from app.modules.auth.models import (
    User,
    UserContact,
    UserIdentity,
    UserProfile,
    UserSession,
    VerificationCode,
    AuthProvider,
    ContactType,
    UserRole,
)
from app.modules.auth.sms import SmsService


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # =====================================================
    # UTILS
    # =====================================================
    OTP_EXPIRE_MINUTES = 5
    OTP_RESEND_COOLDOWN_SECONDS = 60
    OTP_MAX_ATTEMPTS = 5

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    async def _get_user_full(self, user_id: int) -> User:
        stmt = (
            select(User)
            .options(
                selectinload(User.contacts),
                selectinload(User.identities),
                selectinload(User.profile),
            )
            .where(User.id == user_id)
        )
        result = await self.db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user

    # =====================================================
    # TOKEN & SESSION
    # =====================================================

    async def _create_session_and_tokens(
        self,
        user: User,
        request: Request,
        family_id: Optional[str] = None,
    ) -> Token:
        access_token = create_access_token(
            user_id=user.id,
            extra_data={"role": user.global_role.value},
        )

        refresh_token = secrets.token_urlsafe(64)
        refresh_hash = self._hash(refresh_token)

        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            user_agent=request.headers.get("user-agent", "unknown")[:255],
            ip_address=request.client.host if request.client else "unknown",
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )

        self.db.add(session)
        await self.db.flush()

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    # =====================================================
    # SOCIAL CORE (GOOGLE & TELEGRAM)
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
    ) -> Token:
        async with self.db.begin():
            # 1. Identity orqali tekshirish
            stmt = select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_id == provider_id,
            )
            identity = (await self.db.execute(stmt)).scalar_one_or_none()

            if identity:
                user = await self._get_user_full(identity.user_id)
                # Profilni yangilash
                if user.profile:
                    if full_name:
                        user.profile.full_name = full_name
                    if avatar_url:
                        user.profile.avatar_url = avatar_url
                    if username:
                        user.profile.username = username  # Agar Profile'da bo'lsa
                return await self._create_session_and_tokens(user, request)

            # 2. Username tayyorlash
            if not username:
                base = email.split("@")[0] if email else "user"
                username = f"{base}_{secrets.randbelow(9999)}"

            # 3. User yaratish (Username'siz!)
            user = User(
                id=secrets.randbelow(90_000_000) + 10_000_000,
                global_role=UserRole.USER,
                is_active=True,
            )
            self.db.add(user)
            await self.db.flush()

            # 4. Profil yaratish (USERNAME SHU YERGA QO'SHILDI)
            user_profile = UserProfile(
                user_id=user.id,
                full_name=full_name,
                avatar_url=avatar_url,
                username=username.lower(),  # <--- Username shu yerda bo'lishi kerak
            )
            self.db.add(user_profile)

            # 5. Identity bog'lash
            self.db.add(
                UserIdentity(
                    user_id=user.id,
                    provider=provider,
                    provider_id=provider_id,
                )
            )

            # 6. Kontakt bog'lash
            if email:
                self.db.add(
                    UserContact(
                        user_id=user.id,
                        contact_type=ContactType.EMAIL,
                        value=email.lower(),
                        is_verified=True,
                        is_primary=True,
                    )
                )

            try:
                await self.db.flush()
            except IntegrityError:
                # Agar UserProfile'dagi username band bo'lsa
                user_profile.username = (
                    f"{user_profile.username}_{secrets.randbelow(999)}"
                )
                await self.db.flush()

            full_user = await self._get_user_full(user.id)
            return await self._create_session_and_tokens(full_user, request)

    # =====================================================
    # GOOGLE LOGIN
    # =====================================================

    async def verify_google_token(self, token: str):
        try:
            return id_token.verify_oauth2_token(
                token, requests.Request(), settings.GOOGLE_CLIENT_ID
            )
        except ValueError:
            raise HTTPException(status_code=401, detail="Google token yaroqsiz")

    async def google_login(self, data: GoogleLoginRequest, request: Request) -> Token:
        g_data = await self.verify_google_token(data.id_token)
        return await self._social_auth(
            provider=AuthProvider.GOOGLE,
            provider_id=g_data["sub"],
            email=g_data.get("email"),
            full_name=g_data.get("name"),
            avatar_url=g_data.get("picture"),
            request=request,
        )

    # =====================================================
    # TELEGRAM LOGIN
    # =====================================================

    async def telegram_login(
        self, data: TelegramLoginRequest, request: Request
    ) -> Token:
        if not self._verify_telegram_hash(data):
            raise HTTPException(401, "Telegram autentifikatsiya xato")

        full_name = f"{data.first_name or ''} {data.last_name or ''}".strip()
        return await self._social_auth(
            provider=AuthProvider.TELEGRAM,
            provider_id=str(data.id),
            username=data.username,
            full_name=full_name,
            avatar_url=data.photo_url,
            request=request,
        )

    def _verify_telegram_hash(self, data: TelegramLoginRequest) -> bool:
        data_dict = data.model_dump(exclude={"hash"})
        check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data_dict.items()) if v is not None
        )
        secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
        calculated_hash = hmac.new(
            secret_key, check_string.encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(calculated_hash, data.hash)

    # =====================================================
    # PHONE & OTP
    # =====================================================

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def _verify_hash(self, plain: str, hashed: str) -> bool:
        return hmac.compare_digest(self._hash(plain), hashed)

    async def send_otp(self, phone: str, source: str = "web") -> dict:
        """
        source:
          - "web": SMS yuboradi
          - "bot": SMS yubormaydi, faqat code qaytaradi (bot userga yuboradi)
        """

        now = datetime.now(timezone.utc)

        # 1) Cooldown tekshirish
        stmt = select(VerificationCode).where(
            VerificationCode.target == phone,
            VerificationCode.created_at
            > now - timedelta(seconds=self.OTP_RESEND_COOLDOWN_SECONDS),
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()

        if existing:
            raise HTTPException(429, "Too many requests")

        # 2) Kod yaratish
        code = str(secrets.randbelow(900000) + 100000)

        # 3) Eski kodlarni o'chirish
        await self.db.execute(
            delete(VerificationCode).where(VerificationCode.target == phone)
        )

        # 4) Yangi record
        record = VerificationCode(
            target=phone,
            code_hash=self._hash(code),
            expires_at=now + timedelta(minutes=self.OTP_EXPIRE_MINUTES),
            failed_attempts=0,
            is_used=False,
            # created_at odatda default bilan qo'yiladi, bo'lmasa uncomment qil:
            # created_at=now,
        )
        self.db.add(record)
        await self.db.commit()

        # 5) SMS matni (escape muammosiz)
        message = (
            f"NarxNav sayti orqali ro‘yxatdan o‘tish uchun tasdiqlash kodingiz: {code}"
        )

        # 6) BOT so'rasa: SMS yubormaymiz
        if source == "bot":
            # bot shu code'ni userga yuboradi
            return {"status": "sent", "code": code}

        # 7) WEB so'rasa: SMS yuboramiz
        await anyio.to_thread.run_sync(
            SmsService.send_otp,
            phone,
            code,
            # Agar SmsService message qabul qilsa:
            # message
        )

        # 8) Production / Dev response
        if settings.ENV.lower() == "production":
            return {"status": "sent"}

        return {"status": "sent", "code": code, "message": message}

    # =====================================================
    # VERIFY
    # =====================================================

    async def _verify_otp(self, phone: str, code: str) -> bool:
        now = datetime.now(timezone.utc)

        stmt = (
            select(VerificationCode)
            .where(
                VerificationCode.target == phone,
                not VerificationCode.is_used,
                VerificationCode.expires_at > now,
            )
            .with_for_update()
        )

        record = (await self.db.execute(stmt)).scalar_one_or_none()

        if not record:
            return False

        if record.failed_attempts >= self.OTP_MAX_ATTEMPTS:
            return False

        if not self._verify_hash(code, record.code_hash):
            record.failed_attempts += 1
            return False

        record.is_used = True
        return True

    # =====================================================
    # AUTHENTICATE
    # =====================================================

    async def authenticate_by_phone(
        self, phone: str, code: str, request: Request
    ) -> PhoneAuthResponse:

        async with self.db.begin():
            if not await self._verify_otp(phone, code):
                raise HTTPException(400, "Kod noto'g'ri yoki eskirgan")

            stmt = select(UserContact).where(
                and_(
                    UserContact.contact_type == ContactType.PHONE,
                    UserContact.value == phone,
                )
            )

            contact = (await self.db.execute(stmt)).scalar_one_or_none()

            if not contact:
                return PhoneAuthResponse(status="need_registration")

            user = await self._get_user_full(contact.user_id)

            tokens = await self._create_session_and_tokens(user, request)

            return PhoneAuthResponse(status="success", token=tokens)

    # =====================================================
    # LOGOUT
    # =====================================================

    async def logout(self, user_id: int, request: Request):
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "unknown")[:255]
        await self.db.execute(
            delete(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.ip_address == ip,
                UserSession.user_agent == ua,
            )
        )
        await self.db.commit()

    async def refresh(self, refresh_token: str, request: Request) -> Token:
        now = datetime.now(timezone.utc)
        refresh_hash = self._hash(refresh_token)

        async with self.db.begin():
            stmt = (
                select(UserSession)
                .where(UserSession.refresh_token_hash == refresh_hash)
                .with_for_update()
            )
            session = (await self.db.execute(stmt)).scalar_one_or_none()

            if not session:
                raise HTTPException(401, "Invalid refresh token")

            if session.is_revoked:
                # 🔥 reuse attack
                await self._revoke_family(session.session_family_id)
                raise HTTPException(401, "Token reuse detected")

            if session.expires_at < now:
                session.is_revoked = True
                raise HTTPException(401, "Expired")

            user = await self._get_user_full(session.user_id)

            new_token = await self._create_session_and_tokens(
                user=user,
                request=request,
                session_family_id=session.session_family_id,
            )

            # eski revoke
            session.is_revoked = True
            session.replaced_by_id = None  # optional

            return new_token

    async def _revoke_family(self, family_id: uuid.UUID):
        await self.db.execute(
            update(UserSession)
            .where(UserSession.session_family_id == family_id)
            .values(is_revoked=True)
        )

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
        refresh_hash = self._hash(refresh_token)

        session = UserSession(
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            family_id=user.session_family_id,  # 🔥 TO‘G‘RI
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            expires_at=datetime.now(timezone.utc)
            + timedelta(days=settings.REFRESH_TOKEN_DAYS),
        )

        self.db.add(session)
        await self.db.flush()

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
        )