import secrets
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import HTTPException, Request, status
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

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # =====================================================
    # UTILS
    # =====================================================

    def _hash(self, value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    async def _get_user_full(self, user_id: int) -> User:
        stmt = (
            select(User)
            .options(
                selectinload(User.contacts),
                selectinload(User.identities),
                selectinload(User.profile)
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

    async def _create_session_and_tokens(self, user: User, request: Request) -> Token:
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
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_DAYS),
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
                    if full_name: user.profile.full_name = full_name
                    if avatar_url: user.profile.avatar_url = avatar_url
                    if username: user.profile.username = username # Agar Profile'da bo'lsa
                return await self._create_session_and_tokens(user, request)

            # 2. Username tayyorlash
            if not username:
                base = email.split('@')[0] if email else "user"
                username = f"{base}_{secrets.randbelow(9999)}"

            # 3. User yaratish (Username'siz!)
            user = User(
                id=secrets.randbelow(90_000_000) + 10_000_000,
                global_role=UserRole.USER,
                is_active=True
            )
            self.db.add(user)
            await self.db.flush()

            # 4. Profil yaratish (USERNAME SHU YERGA QO'SHILDI)
            user_profile = UserProfile(
                user_id=user.id,
                full_name=full_name,
                avatar_url=avatar_url,
                username=username.lower()  # <--- Username shu yerda bo'lishi kerak
            )
            self.db.add(user_profile)

            # 5. Identity bog'lash
            self.db.add(UserIdentity(
                user_id=user.id,
                provider=provider,
                provider_id=provider_id,
            ))

            # 6. Kontakt bog'lash
            if email:
                self.db.add(UserContact(
                    user_id=user.id,
                    contact_type=ContactType.EMAIL,
                    value=email.lower(),
                    is_verified=True,
                    is_primary=True,
                ))

            try:
                await self.db.flush()
            except IntegrityError:
                # Agar UserProfile'dagi username band bo'lsa
                user_profile.username = f"{user_profile.username}_{secrets.randbelow(999)}"
                await self.db.flush()

            full_user = await self._get_user_full(user.id)
            return await self._create_session_and_tokens(full_user, request)

    # =====================================================
    # GOOGLE LOGIN
    # =====================================================

    async def verify_google_token(self, token: str):
        try:
            return id_token.verify_oauth2_token(token, requests.Request(), settings.GOOGLE_CLIENT_ID)
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

    async def telegram_login(self, data: TelegramLoginRequest, request: Request) -> Token:
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
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(data_dict.items()) if v is not None)
        secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
        calculated_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(calculated_hash, data.hash)

    # =====================================================
    # PHONE & OTP
    # =====================================================

    async def send_otp(self, phone: str) -> Dict:
        now = datetime.now(timezone.utc)
        stmt = select(VerificationCode).where(
            VerificationCode.target == phone,
            VerificationCode.created_at > now - timedelta(minutes=1)
        )
        if (await self.db.execute(stmt)).scalar_one_or_none():
            raise HTTPException(429, "Juda tez-tez so'rov yuboryapsiz")

        code = str(secrets.randbelow(9000) + 1000)
        await self.db.execute(delete(VerificationCode).where(VerificationCode.target == phone))

        self.db.add(VerificationCode(
            target=phone,
            code_hash=self._hash(code),
            expires_at=now + timedelta(minutes=5),
        ))
        await self.db.commit()
        return {"status": "sent", "debug_code": code if settings.DEBUG else None}

    async def _verify_otp(self, phone: str, code: str) -> bool:
        stmt = (
            update(VerificationCode)
            .where(
                VerificationCode.target == phone,
                VerificationCode.code_hash == self._hash(code),
                VerificationCode.is_used == False,
                VerificationCode.expires_at > datetime.now(timezone.utc),
            )
            .values(is_used=True)
            .returning(VerificationCode.id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def authenticate_by_phone(self, phone: str, code: str, request: Request) -> PhoneAuthResponse:
        async with self.db.begin():
            if not await self._verify_otp(phone, code):
                raise HTTPException(400, "Kod noto'g'ri yoki eskirgan")

            stmt = select(UserContact).where(
                and_(UserContact.contact_type == ContactType.PHONE, UserContact.value == phone)
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