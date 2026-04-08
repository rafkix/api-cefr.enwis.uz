from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.service import AuthService
from app.modules.auth.dependencies import get_current_user

from app.modules.auth.schemas import (
    GoogleLoginRequest,
    TelegramLoginRequest,
    PhoneLoginRequest,
    SendCodeRequest,
    PhoneAuthResponse,
    StatusResponse,
)

from app.modules.users.schemas import UserResponse
from app.modules.auth.models import User


router = APIRouter(prefix="/auth", tags=["Auth"])


# =====================================================
# DEPENDENCY
# =====================================================


def get_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(db)


# =====================================================
# COOKIE (🔥 CORE SSO)
# =====================================================


def set_auth_cookies(response: Response, tokens):
    response.set_cookie(
        key="access_token",
        value=tokens.access_token,
        httponly=True,
        secure=True,
        samesite="lax",
        domain=".enwis.uz",  # 🔥 barcha subdomainlar uchun
        path="/",
        max_age=60 * 15,
    )

    response.set_cookie(
        key="refresh_token",
        value=tokens.refresh_token,
        httponly=True,
        secure=True,
        samesite="lax",
        domain=".enwis.uz",
        path="/",
        max_age=60 * 60 * 24 * 30,
    )


def clear_auth_cookies(response: Response):
    response.delete_cookie("access_token", domain=".enwis.uz", path="/")
    response.delete_cookie("refresh_token", domain=".enwis.uz", path="/")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


@router.post("/refresh", response_model=StatusResponse)
async def refresh(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
):
    refresh_token = request.cookies.get("refresh_token")

    if not refresh_token:
        raise HTTPException(401, "Refresh token missing")

    tokens = await service.refresh(refresh_token, request)

    set_auth_cookies(response, tokens.dict())

    return StatusResponse(status="success", message="Refreshed")


@router.post("/otp/send", response_model=StatusResponse)
async def send_otp(
    data: SendCodeRequest,
    service: AuthService = Depends(get_service),
):
    await service.send_otp(data.phone)
    return StatusResponse(status="success", message="Kod yuborildi")


@router.post("/otp/send/bot", response_model=StatusResponse)
async def send_otp_bot(
    data: SendCodeRequest,
    service: AuthService = Depends(get_service),
):
    await service.send_otp(data.phone, source="bot")
    return StatusResponse(status="success")


@router.post("/phone/login", response_model=PhoneAuthResponse)
async def phone_login(
    data: PhoneLoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
):
    result = await service.authenticate_by_phone(
        phone=data.phone,
        code=data.code,
        request=request,
    )

    if result.status == "success" and result.token:
        set_auth_cookies(response, result.token)

    return result


@router.post("/google", response_model=StatusResponse)
async def google_login(
    data: GoogleLoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
):
    tokens = await service.google_login(data, request)
    set_auth_cookies(response, tokens)

    return StatusResponse(status="success")


@router.post("/telegram", response_model=StatusResponse)
async def telegram_login(
    data: TelegramLoginRequest,
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
):
    tokens = await service.telegram_login(data, request)
    set_auth_cookies(response, tokens)

    return StatusResponse(status="success")


@router.post("/logout", response_model=StatusResponse)
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_service),
):
    refresh_token = request.cookies.get("refresh_token")

    if refresh_token:
        await service.logout(refresh_token)

    clear_auth_cookies(response)

    return StatusResponse(status="success", message="Logged out")
