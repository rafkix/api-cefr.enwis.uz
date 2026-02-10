import secrets
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict
from sqlalchemy.exc import IntegrityError

from fastapi import HTTPException, Request
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_password, verify_password, create_access_token
from app.core.config import settings
from app.modules.auth.schemas import (
    Token, RegisterRequest, LoginRequest, TelegramLoginRequest, 
    GoogleLoginRequest, PhoneAuthResponse, PhoneRegistrationComplete
)
from app.modules.auth.models import (
    User, UserProfile, UserContact, UserIdentity, 
    UserSession, VerificationCode, AuthProvider, VerificationPurpose
)
from app.modules.users.schemas import UserRole

class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_full_user(self, user_id: int) -> User:
        stmt = select(User).options(
            selectinload(User.profile),
            selectinload(User.contacts),
            selectinload(User.identities)
        ).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _generate_user_id(self) -> int:
        while True:
            u_id = secrets.randbelow(9_000_000) + 1_000_000
            stmt = select(User.id).where(User.id == u_id)
            if not (await self.db.execute(stmt)).scalar():
                return u_id


    async def _generate_unique_username(self, base_name: Optional[str], user_id: int) -> str:
        if not base_name: 
            return f"user_{user_id}"
        clean_name = "".join(e for e in base_name if e.isalnum() or e == "_").lower()
        stmt = select(UserProfile).where(UserProfile.username == clean_name)
        exists = (await self.db.execute(stmt)).scalar()
        return clean_name if not exists else f"{clean_name}_{str(user_id)[-3:]}"

    def _verify_telegram_hash(self, data: TelegramLoginRequest) -> bool:
        if not settings.TELEGRAM_BOT_TOKEN:
            raise HTTPException(status_code=500, detail="Telegram bot token sozlanmagan")
        data_dict = data.model_dump(exclude={'hash'})
        check_string = "\n".join([f"{k}={v}" for k, v in sorted(data_dict.items()) if v is not None])
        secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
        hash_result = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hash_result == data.hash

    async def create_tokens(self, user: User, request: Request) -> Token:
        """Seans yaratish va JWT tokenlarni qaytarish."""
        # JWT Access Token yaratish
        access = create_access_token(
            user_id=user.id, 
            extra_data={
                "username": user.profile.username if user.profile else None, 
                "role": user.global_role.value
            }
        )
        
        # Refresh Token yaratish
        refresh = secrets.token_urlsafe(64)
        refresh_hash = hashlib.sha256(refresh.encode()).hexdigest()
        
        # Bazada yangi seans (session) yaratish
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            user_agent=request.headers.get("user-agent", "unknown"),
            ip_address=request.client.host if request.client else "unknown",
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_DAYS)
        )
        self.db.add(session)
        # Session ID bazaga tushishi uchun flush qilamiz
        await self.db.flush()
        
        return Token(access_token=access, refresh_token=refresh, token_type="bearer")

    async def register(self, data: RegisterRequest, request: Request) -> Token:
        try:
            uid = await self._generate_user_id()
            user = User(id=uid, global_role=UserRole.USER)
            self.db.add(user)
            await self.db.flush()

            self.db.add(UserProfile(
                user_id=uid,
                full_name=data.full_name,
                username=data.username.lower() if data.username else await self._generate_unique_username(data.full_name, uid)
            ))

            self.db.add_all([
                UserContact(user_id=uid, contact_type="email", value=data.email, is_primary=True),
                UserContact(user_id=uid, contact_type="phone", value=data.phone, is_primary=True)
            ])

            self.db.add(UserIdentity(
                user_id=uid,
                provider=AuthProvider.LOCAL,
                provider_id=data.email,
                password_hash=hash_password(data.password)
            ))

            await self.db.flush()

        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(400, "Bu email allaqachon ro'yxatdan o'tgan")

        full_user = await self._get_full_user(uid)
        tokens = await self.create_tokens(full_user, request)

        await self.db.commit()
        return tokens


    async def authenticate(self, data: LoginRequest, request: Request) -> Token:
        """Login va parol orqali kirish."""
        stmt = select(UserIdentity).where(
            or_(
                UserIdentity.provider_id == data.login.lower(), 
                UserIdentity.user_id.in_(select(UserProfile.user_id).where(UserProfile.username == data.login.lower()))
            ),
            UserIdentity.provider == AuthProvider.LOCAL
        )
        identity = (await self.db.execute(stmt)).scalar_one_or_none()
        
        if not identity or not identity.password_hash or not verify_password(data.password, identity.password_hash):
            raise HTTPException(401, "Login yoki parol noto'g'ri")
            
        user = await self._get_full_user(identity.user_id)
        tokens = await self.create_tokens(user, request)
        await self.db.commit()
        return tokens

    async def google_login(self, data: GoogleLoginRequest, request: Request) -> Token:
        return await self._social_auth_logic(
            provider=AuthProvider.GOOGLE, 
            p_id=data.google_id, 
            name=data.name, 
            username_suggestion=data.email.split('@')[0], 
            request=request,
            avatar=data.picture
        )

    async def telegram_login(self, data: TelegramLoginRequest, request: Request) -> Token:
        if not self._verify_telegram_hash(data): 
            raise HTTPException(401, "Telegram xavfsizlik tekshiruvidan o'tmadi")
            
        return await self._social_auth_logic(
            provider=AuthProvider.TELEGRAM, 
            p_id=str(data.id), 
            name=f"{data.first_name} {data.last_name or ''}".strip(), 
            username_suggestion=data.username, 
            request=request,
            avatar=data.photo_url
        )

    async def _social_auth_logic(
        self,
        provider: AuthProvider,
        p_id: str,
        name: str,
        username_suggestion: Optional[str],
        request: Request,
        avatar: Optional[str] = None
    ) -> Token:

        stmt = select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_id == p_id
        )
        identity = (await self.db.execute(stmt)).scalar_one_or_none()

        if identity:
            user = await self._get_full_user(identity.user_id)
            tokens = await self.create_tokens(user, request)
            await self.db.commit()
            return tokens

        try:
            uid = await self._generate_user_id()
            user = User(id=uid)
            self.db.add(user)
            await self.db.flush()

            self.db.add(UserProfile(
                user_id=uid,
                full_name=name,
                username=await self._generate_unique_username(username_suggestion, uid),
                avatar_url=avatar
            ))

            self.db.add(UserIdentity(
                user_id=uid,
                provider=provider,
                provider_id=p_id
            ))

            await self.db.flush()

        except IntegrityError:
            # boshqa request user yaratib ulgurgan
            await self.db.rollback()

            stmt = select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_id == p_id
            )
            identity = (await self.db.execute(stmt)).scalar_one()

            user = await self._get_full_user(identity.user_id)
            tokens = await self.create_tokens(user, request)
            await self.db.commit()
            return tokens

        full_user = await self._get_full_user(uid)
        tokens = await self.create_tokens(full_user, request)

        await self.db.commit()
        return tokens

    async def authenticate_by_phone(self, phone: str, code: str, request: Request) -> PhoneAuthResponse:
        """Telefon va kod orqali kirish."""
        v_stmt = select(VerificationCode).where(
            VerificationCode.target == phone, 
            VerificationCode.code == code, 
            VerificationCode.is_used == False, 
            VerificationCode.expires_at > datetime.now(timezone.utc)
        )
        v_code = (await self.db.execute(v_stmt)).scalar_one_or_none()
        if not v_code: 
            raise HTTPException(400, "Kod xato yoki eskirgan")
        
        contact = (await self.db.execute(select(UserContact).where(UserContact.value == phone))).scalar_one_or_none()
        
        if not contact: 
            return PhoneAuthResponse(status="need_registration", message="Foydalanuvchi topilmadi, iltimos ro'yxatdan o'ting")

        v_code.is_used = True
        user = await self._get_full_user(contact.user_id)
        tokens = await self.create_tokens(user, request)
        await self.db.commit()
        return PhoneAuthResponse(status="success", token=tokens)

    async def complete_phone_registration(self, data: PhoneRegistrationComplete, request: Request) -> Token:
        """Telefon orqali ro'yxatdan o'tishni yakunlash."""
        v_code = (await self.db.execute(select(VerificationCode).where(
            VerificationCode.target == data.phone, 
            VerificationCode.code == data.code, 
            VerificationCode.is_used == False
        ))).scalar_one_or_none()
        
        if not v_code: 
            raise HTTPException(400, "Tasdiqlash kodi yaroqsiz")

        uid = await self._generate_user_id()
        user = User(id=uid)
        self.db.add(user)
        await self.db.flush()

        self.db.add_all([
            UserProfile(user_id=uid, full_name=data.full_name, username=await self._generate_unique_username(data.username, uid)),
            UserContact(user_id=uid, contact_type="phone", value=data.phone, is_primary=True)
        ])
        
        if data.email:
            self.db.add(UserContact(user_id=uid, contact_type="email", value=data.email, is_primary=True))
            
        v_code.is_used = True
        await self.db.flush()
        
        full_user = await self._get_full_user(uid)
        tokens = await self.create_tokens(full_user, request)
        await self.db.commit()
        return tokens

    async def send_verification_code(self, target: str, purpose: VerificationPurpose) -> Dict:
        """SMS/Email kod yuborish."""
        code = str(secrets.randbelow(9000) + 1000)
        # Eskirgan kodlarni o'chirish
        await self.db.execute(delete(VerificationCode).where(VerificationCode.target == target))
        
        self.db.add(VerificationCode(
            target=target, 
            code=code, 
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), 
            purpose=purpose
        ))
        await self.db.commit()
        
        # Real loyihada bu yerda SMS provayder (masalan, Eskiz) chaqiriladi
        return {"method": "sms" if target.startswith("+") else "email", "debug_code": code}