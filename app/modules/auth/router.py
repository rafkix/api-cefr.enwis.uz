from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import AuthService
from app.modules.auth.models import User
from app.modules.auth.schemas import (Token, RegisterRequest, LoginRequest, 
    GoogleLoginRequest, TelegramLoginRequest, PhoneLoginRequest,
    PhoneAuthResponse, PhoneRegistrationComplete, SendCodeRequest
)
from app.modules.users.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=Token)
async def register(
    data: RegisterRequest, 
    request: Request,  # <--- Bu qator muhim
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    # Servisga data va request'ni yuboramiz
    tokens = await service.register(data, request) 
    return tokens

@router.post("/login", response_model=Token)
async def login(
    data: LoginRequest, 
    request: Request,  # <--- Login uchun ham kerak
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    tokens = await service.authenticate(data, request)
    return tokens

@router.post("/google", response_model=Token)
async def google_login(
    data: GoogleLoginRequest, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    """Google orqali kirish yoki ro'yxatdan o'tish."""
    service = AuthService(db)
    tokens = await service.google_login(data, request) 
    return tokens

@router.post("/telegram", response_model=Token)
async def telegram_login(
    data: TelegramLoginRequest, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    """Telegram orqali kirish yoki ro'yxatdan o'tish."""
    service = AuthService(db)
    tokens = await service.telegram_login(data, request)
    return tokens

@router.post("/send-code")
async def send_code(data: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    """Telefon yoki Emailga tasdiqlash kodini yuborish."""
    service = AuthService(db)
    result = await service.send_verification_code(data.target, data.purpose)
    return {"message": "Kod yuborildi", **result}

@router.post("/login/phone", response_model=PhoneAuthResponse)
async def login_phone(data: PhoneLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """
    Telefon raqam orqali kirish. 
    Agar user mavjud bo'lsa 'token' qaytadi, bo'lmasa 'need_registration' statusi qaytadi.
    """
    service = AuthService(db)
    return await service.authenticate_by_phone(data.phone, data.code, request)

@router.post("/login/phone/complete", response_model=Token)
async def complete_phone_auth(data: PhoneRegistrationComplete, request: Request, db: AsyncSession = Depends(get_db)):
    """Yangi foydalanuvchi telefon orqali kirganda profilini to'ldirib ro'yxatdan o'tishi."""
    service = AuthService(db)
    return await service.complete_phone_registration(data, request)

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Joriy foydalanuvchi ma'lumotlarini olish."""
    return current_user