import secrets
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from fastapi import HTTPException, Request, status
from sqlalchemy import select, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

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

    # --- YORDAMCHI METODLAR ---

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
            raise HTTPException(500, "Telegram bot token sozlanmagan")
        data_dict = data.model_dump(exclude={'hash'})
        check_string = "\n".join([f"{k}={v}" for k, v in sorted(data_dict.items()) if v is not None])
        secret_key = hashlib.sha256(settings.TELEGRAM_BOT_TOKEN.encode()).digest()
        hash_result = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        return hash_result == data.hash

    # --- ASOSIY LOGIN/REGISTER MANTIQI ---

    async def create_tokens(self, user: User, request: Request) -> Token:
        access = create_access_token(
            user_id=user.id, 
            extra_data={
                "username": user.profile.username if user.profile else None, 
                "role": user.global_role.value
            }
        )
        refresh = secrets.token_urlsafe(64)
        refresh_hash = hashlib.sha256(refresh.encode()).hexdigest()
        
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=refresh_hash,
            user_agent=request.headers.get("user-agent", "unknown")[:255],
            ip_address=request.client.host if request.client else "unknown",
            expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_DAYS)
        )
        self.db.add(session)
        await self.db.flush()
        return Token(access_token=access, refresh_token=refresh, token_type="bearer")

    async def register(self, data: RegisterRequest, request: Request) -> Token:
        try:
            async with self.db.begin_nested(): # Race-condition protection
                uid = await self._generate_user_id()
                user = User(id=uid, global_role=UserRole.USER)
                self.db.add(user)
                
                username = data.username.lower() if data.username else await self._generate_unique_username(data.full_name, uid)
                self.db.add(UserProfile(user_id=uid, full_name=data.full_name, username=username))
                
                self.db.add_all([
                    UserContact(user_id=uid, contact_type="email", value=data.email.lower(), is_primary=True),
                    UserContact(user_id=uid, contact_type="phone", value=data.phone, is_primary=True)
                ])
                self.db.add(UserIdentity(
                    user_id=uid, provider=AuthProvider.LOCAL,
                    provider_id=data.email.lower(), password_hash=hash_password(data.password)
                ))
                await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(400, "Email, telefon yoki username band")

        full_user = await self._get_full_user(uid)
        tokens = await self.create_tokens(full_user, request)
        await self.db.commit()
        return tokens

    async def authenticate(self, data: LoginRequest, request: Request) -> Token:
        stmt = select(UserIdentity).where(
            or_(
                UserIdentity.provider_id == data.login.lower(), 
                UserIdentity.user_id.in_(select(UserProfile.user_id).where(UserProfile.username == data.login.lower()))
            ),
            UserIdentity.provider == AuthProvider.LOCAL
        )
        identity = (await self.db.execute(stmt)).scalar_one_or_none()
        if not identity or not verify_password(data.password, identity.password_hash):
            raise HTTPException(401, "Login yoki parol noto'g'ri")
            
        user = await self._get_full_user(identity.user_id)
        tokens = await self.create_tokens(user, request)
        await self.db.commit()
        return tokens

    # --- IJTIMOIY TARMOQLAR ---

    # 1. GOOGLE LOGIN
    async def google_login(self, data: GoogleLoginRequest, request: Request) -> Token:
        return await self._social_auth_logic(
            provider=AuthProvider.GOOGLE, 
            p_id=data.google_id, 
            name=data.name, 
            username_suggestion=data.email.split('@')[0], 
            request=request,
            avatar=data.picture,
            email=data.email  # <--- Email qo'shildi
        )

    # 2. TELEGRAM LOGIN
    async def telegram_login(self, data: TelegramLoginRequest, request: Request) -> Token:
        """Telegram orqali kirish (Xavfsizlik hashini tekshirgan holda)."""
        if not self._verify_telegram_hash(data): 
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Telegram xavfsizlik tekshiruvidan o'tmadi"
            )
            
        return await self._social_auth_logic(
            provider=AuthProvider.TELEGRAM, 
            p_id=str(data.id), 
            name=f"{data.first_name} {data.last_name or ''}".strip(), 
            username_suggestion=data.username, 
            request=request,
            avatar=data.photo_url
        )

    # 3. UMUMIY SOCIAL MANTIQ (High-Performance & Race-Condition Safe)
    async def _social_auth_logic(
        self,
        provider: AuthProvider,
        p_id: str,
        name: str,
        username_suggestion: Optional[str],
        request: Request,
        avatar: Optional[str] = None,
        email: Optional[str] = None  # <--- Email argumenti
    ) -> Token:
        # 1. Tekshiruv (Mavjud foydalanuvchi)
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

        # 2. Yangi foydalanuvchi yaratish
        try:
            async with self.db.begin_nested():
                uid = await self._generate_user_id()
                user = User(id=uid, global_role=UserRole.USER)
                self.db.add(user)
                
                username = await self._generate_unique_username(username_suggestion, uid)
                
                # Profil ma'lumotlari
                self.db.add(UserProfile(
                    user_id=uid,
                    full_name=name,
                    username=username,
                    avatar_url=avatar
                ))

                # --- MUHIM JOYI: Kontaktlarga saqlash ---
                if email:
                    from your_app.models import UserContact # Model nomiga qarang
                    self.db.add(UserContact(
                        user_id=uid,
                        contact_type="email",
                        value=email,
                        is_verified=True,  # Google'dan kelgan email tasdiqlangan bo'ladi
                        is_primary=True
                    ))

                # Identity (Google/Telegram ID bog'lash)
                self.db.add(UserIdentity(
                    user_id=uid,
                    provider=provider,
                    provider_id=p_id
                ))
                await self.db.flush()

        except IntegrityError:
            await self.db.rollback()
            identity = (await self.db.execute(stmt)).scalar_one()
            uid = identity.user_id

        full_user = await self._get_full_user(uid)
        tokens = await self.create_tokens(full_user, request)
        await self.db.commit()
        return tokens

    # --- TELEFON VA VERIFIKATSIYA ---

    async def authenticate_by_phone(self, phone: str, code: str, request: Request) -> PhoneAuthResponse:
        v_stmt = select(VerificationCode).where(
            VerificationCode.target == phone, VerificationCode.code == code, 
            VerificationCode.is_used == False, VerificationCode.expires_at > datetime.now(timezone.utc)
        )
        v_code = (await self.db.execute(v_stmt)).scalar_one_or_none()
        if not v_code: raise HTTPException(400, "Kod xato yoki eskirgan")
        
        contact = (await self.db.execute(select(UserContact).where(UserContact.value == phone))).scalar_one_or_none()
        if not contact: return PhoneAuthResponse(status="need_registration", message="Ro'yxatdan o'ting")

        v_code.is_used = True
        user = await self._get_full_user(contact.user_id)
        tokens = await self.create_tokens(user, request)
        await self.db.commit()
        return PhoneAuthResponse(status="success", token=tokens)

    async def complete_phone_registration(self, data: PhoneRegistrationComplete, request: Request) -> Token:
        v_code = (await self.db.execute(select(VerificationCode).where(
            VerificationCode.target == data.phone, VerificationCode.code == data.code, VerificationCode.is_used == False
        ))).scalar_one_or_none()
        if not v_code: raise HTTPException(400, "Kod yaroqsiz")

        try:
            async with self.db.begin_nested():
                uid = await self._generate_user_id()
                self.db.add(User(id=uid))
                username = await self._generate_unique_username(data.username, uid)
                self.db.add(UserProfile(user_id=uid, full_name=data.full_name, username=username))
                self.db.add(UserContact(user_id=uid, contact_type="phone", value=data.phone, is_primary=True))
                if data.email:
                    self.db.add(UserContact(user_id=uid, contact_type="email", value=data.email.lower(), is_primary=True))
                v_code.is_used = True
                await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(400, "Username yoki ma'lumotlar band")

        full_user = await self._get_full_user(uid)
        tokens = await self.create_tokens(full_user, request)
        await self.db.commit()
        return tokens

    async def send_verification_code(self, target: str, purpose: VerificationPurpose) -> Dict:
        code = str(secrets.randbelow(9000) + 1000)
        await self.db.execute(delete(VerificationCode).where(VerificationCode.target == target))
        self.db.add(VerificationCode(
            target=target, code=code, 
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), purpose=purpose
        ))
        await self.db.commit()
        return {"method": "sms" if target.startswith("+") else "email", "debug_code": code}

    async def add_phone_to_social_account(self, user_id: int, phone: str) -> Dict:
        """Social login orqali kirgan foydalanuvchiga telefon raqami biriktirish."""
        
        # 1. Raqam bandligini tekshirish
        stmt = select(UserContact).where(
            UserContact.value == phone,
            UserContact.contact_type == "phone"
        )
        existing_contact = (await self.db.execute(stmt)).scalar_one_or_none()
        
        if existing_contact:
            # Agar raqam boshqa birovga tegishli bo'lsa xato beramiz
            if existing_contact.user_id != user_id:
                raise HTTPException(
                    status_code=400, 
                    detail="Bu telefon raqami boshqa foydalanuvchiga biriktirilgan"
                )
            # Agar o'zining raqami bo'lsa, shunchaki muvaffaqiyat qaytaramiz
            return {"status": "success", "message": "Raqam allaqachon biriktirilgan"}

        try:
            async with self.db.begin_nested():
                # 2. Yangi kontakt qo'shish
                new_contact = UserContact(
                    user_id=user_id,
                    contact_type="phone",
                    value=phone,
                    is_primary=True  # Bu foydalanuvchining asosiy raqami bo'ladi
                )
                self.db.add(new_contact)
                await self.db.flush()
            
            await self.db.commit()
            return {"status": "success", "message": "Telefon raqami muvaffaqiyatli saqlandi"}

        except IntegrityError:
            await self.db.rollback()
            raise HTTPException(400, "Xatolik yuz berdi, iltimos qaytadan urinib ko'ring")
    
    async def logout(self, user_id: int, request: Request):
        ip = request.client.host if request.client else "unknown"
        ua = request.headers.get("user-agent", "unknown")[:255]
        await self.db.execute(delete(UserSession).where(
            UserSession.user_id == user_id, UserSession.ip_address == ip, UserSession.user_agent == ua
        ))
        await self.db.commit()