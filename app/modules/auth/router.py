from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import AuthService
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User

from app.modules.auth.schemas import (
    Token,
    GoogleLoginRequest,
    TelegramLoginRequest,
    PhoneLoginRequest,
    PhoneAuthResponse,
    SendCodeRequest,
)

from app.modules.users.schemas import UserResponse


router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)


# =====================================================
# Dependency
# =====================================================

def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    return AuthService(db)


# =====================================================
# GOOGLE LOGIN
# =====================================================

@router.post(
    "/google",
    response_model=Token,
)
async def google_login(
    data: GoogleLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.google_login(data, request)


# =====================================================
# TELEGRAM LOGIN
# =====================================================

@router.post(
    "/telegram",
    response_model=Token,
)
async def telegram_login(
    data: TelegramLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.telegram_login(data, request)


# =====================================================
# SEND OTP (WEB → SMS)
# =====================================================

@router.post(
    "/send-otp",
    status_code=status.HTTP_200_OK,
)
async def send_otp(
    data: SendCodeRequest,
    service: AuthService = Depends(get_auth_service),
):
    # default = web → SMS yuboradi
    return await service.send_otp(data.phone, source="web")

# =====================================================
# SEND OTP (BOT → NO SMS)
# =====================================================
    
@router.post(
    "/bot/send-otp",
    status_code=status.HTTP_200_OK,
)
async def bot_send_otp(
    data: SendCodeRequest,
    service: AuthService = Depends(get_auth_service),
):
    # bot orqali → SMS bloklanadi
    return await service.send_otp(data.phone, source="bot")


# =====================================================
# PHONE LOGIN
# =====================================================

@router.post(
    "/login/phone",
    response_model=PhoneAuthResponse,
)
async def login_by_phone(
    data: PhoneLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.authenticate_by_phone(
        phone=data.phone,
        code=data.code,
        request=request,
    )


# =====================================================
# CURRENT USER
# =====================================================

@router.get(
    "/me",
    response_model=UserResponse,
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


# =====================================================
# LOGOUT
# =====================================================

@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    await service.logout(
        user_id=current_user.id,
        request=request,
    )
    return {"status": "success"}
