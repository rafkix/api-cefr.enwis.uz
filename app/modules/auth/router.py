from fastapi import APIRouter, Depends, Request, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError # Parallel so'rovlardagi xatolar uchun

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.service import AuthService
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    Token, RegisterRequest, LoginRequest, 
    GoogleLoginRequest, TelegramLoginRequest, PhoneLoginRequest,
    PhoneAuthResponse, PhoneRegistrationComplete, SendCodeRequest
)
from app.modules.users.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["Auth"])

# 1. Register - 201 Created statusi bilan
@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    # Servis ichida IntegrityError (unique constraint) ushlanadi
    return await service.register(data, request)

# 2. Login - 200 OK
@router.post("/login", response_model=Token)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.authenticate(data, request)

# 3. Google & Telegram - Bular "Atomic" ishlashi shart
@router.post("/google", response_model=Token)
async def google_login(data: GoogleLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.google_login(data, request)

@router.post("/telegram", response_model=Token)
async def telegram_login(data: TelegramLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.telegram_login(data, request)

# 4. Phone Authentication
@router.post("/send-code")
async def send_code(data: SendCodeRequest, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    result = await service.send_verification_code(data.target, data.purpose)
    return {"message": "Kod yuborildi", **result}

@router.post("/login/phone", response_model=PhoneAuthResponse)
async def login_phone(data: PhoneLoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.authenticate_by_phone(data.phone, data.code, request)

@router.post("/login/phone/complete", response_model=Token, status_code=status.HTTP_201_CREATED)
async def complete_phone_auth(data: PhoneRegistrationComplete, request: Request, db: AsyncSession = Depends(get_db)):
    service = AuthService(db)
    return await service.complete_phone_registration(data, request)

# 5. User Info & Logout
@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.post("/logout")
async def logout(
    request: Request, # Joriy qurilmani aniqlash uchun kerak
    current_user: User = Depends(get_current_user), 
    db: AsyncSession = Depends(get_db)
):
    service = AuthService(db)
    await service.logout(current_user.id, request)
    return {"status": "success", "message": "Successfully logged out"}