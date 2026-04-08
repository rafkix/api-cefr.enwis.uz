from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    AuthLoginResponse,
    AuthorizeRedirectResponse,
    DashboardRedirectResponse,
    ExchangeTokenRequest,
    GoogleLoginRequest,
    LogoutByTokenRequest,
    PhoneAuthResponse,
    PhoneLoginRequest,
    PhoneRegisterRequest,
    RefreshTokenRequest,
    SendCodeRequest,
    SessionResponse,
    StatusResponse,
    TelegramLoginRequest,
    Token,
    UserResponse,
)
from app.modules.auth.service import AuthService


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
# CURRENT USER
# =====================================================


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    return current_user


# =====================================================
# ROLE-BASED DASHBOARD REDIRECT INFO
# =====================================================


@router.get(
    "/dashboard-redirect",
    response_model=DashboardRedirectResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dashboard_redirect(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return DashboardRedirectResponse(
        role=current_user.global_role,
        redirect_to=service.resolve_dashboard_url(current_user),
    )


# =====================================================
# ACTIVE SESSIONS
# =====================================================


@router.get(
    "/sessions",
    response_model=list[SessionResponse],
    status_code=status.HTTP_200_OK,
)
async def get_sessions(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    return await service.get_active_sessions(current_user.id)


# =====================================================
# GOOGLE LOGIN
# =====================================================


@router.post(
    "/google",
    response_model=AuthLoginResponse,
    status_code=status.HTTP_200_OK,
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
    response_model=AuthLoginResponse,
    status_code=status.HTTP_200_OK,
)
async def telegram_login(
    data: TelegramLoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.telegram_login(data, request)


# =====================================================
# SEND OTP (WEB -> SMS)
# =====================================================


@router.post(
    "/send-otp",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
)
async def send_otp(
    data: SendCodeRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    result = await service.send_otp(
        phone=data.phone,
        request=request,
        source="web",
        purpose=data.purpose,
        channel=data.channel,
    )
    return StatusResponse(
        status=result.get("status", "sent"),
        message=result.get("message"),
    )


# =====================================================
# SEND OTP (BOT -> NO SMS)
# =====================================================


@router.post(
    "/bot/send-otp",
    status_code=status.HTTP_200_OK,
)
async def bot_send_otp(
    data: SendCodeRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.send_otp(
        phone=data.phone,
        request=request,
        source="bot",
        purpose=data.purpose,
        channel=data.channel,
    )


# =====================================================
# PHONE LOGIN
# =====================================================


@router.post(
    "/login/phone",
    response_model=PhoneAuthResponse,
    status_code=status.HTTP_200_OK,
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
# PHONE REGISTER
# =====================================================


@router.post(
    "/register/phone",
    response_model=AuthLoginResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_by_phone(
    data: PhoneRegisterRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.register_by_phone(
        phone=data.phone,
        full_name=data.full_name,
        request=request,
    )


# =====================================================
# REFRESH TOKEN
# =====================================================


@router.post(
    "/refresh",
    response_model=Token,
    status_code=status.HTTP_200_OK,
)
async def refresh_token(
    data: RefreshTokenRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.refresh_tokens(
        refresh_token=data.refresh_token,
        request=request,
    )


# =====================================================
# AUTHORIZE (SSO)
# =====================================================


@router.get(
    "/authorize",
    response_model=AuthorizeRedirectResponse,
    status_code=status.HTTP_200_OK,
)
async def authorize(
    client_id: str = Query(..., min_length=1, max_length=50),
    redirect_uri: str = Query(..., min_length=1, max_length=500),
    state: str = Query(..., min_length=8, max_length=500),
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    code = await service.create_auth_code(
        user=current_user,
        client_name=client_id,
        redirect_uri=redirect_uri,
    )
    final_redirect = f"{redirect_uri}?code={code}&state={state}"
    return AuthorizeRedirectResponse(redirect_to=final_redirect)


# =====================================================
# AUTHORIZE REDIRECT VARIANT
# =====================================================


@router.get(
    "/authorize/redirect",
    status_code=status.HTTP_302_FOUND,
)
async def authorize_redirect(
    client_id: str = Query(..., min_length=1, max_length=50),
    redirect_uri: str = Query(..., min_length=1, max_length=500),
    state: str = Query(..., min_length=8, max_length=500),
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    code = await service.create_auth_code(
        user=current_user,
        client_name=client_id,
        redirect_uri=redirect_uri,
    )
    final_redirect = f"{redirect_uri}?code={code}&state={state}"
    return RedirectResponse(url=final_redirect, status_code=status.HTTP_302_FOUND)


# =====================================================
# TOKEN EXCHANGE (SSO)
# =====================================================


@router.post(
    "/token/exchange",
    response_model=Token,
    status_code=status.HTTP_200_OK,
)
async def exchange_token(
    data: ExchangeTokenRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
):
    return await service.exchange_auth_code(
        code=data.code,
        client_name=data.client_id,
        redirect_uri=data.redirect_uri,
        request=request,
    )


# =====================================================
# LOGOUT CURRENT SESSION (legacy fallback)
# =====================================================


@router.post(
    "/logout",
    response_model=StatusResponse,
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
    return StatusResponse(status="success", message="Logged out")


# =====================================================
# LOGOUT BY REFRESH TOKEN
# =====================================================


@router.post(
    "/logout/token",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
)
async def logout_by_refresh_token(
    data: LogoutByTokenRequest,
    service: AuthService = Depends(get_auth_service),
):
    await service.logout_by_refresh_token(data.refresh_token)
    return StatusResponse(status="success", message="Session revoked")


# =====================================================
# LOGOUT ALL SESSIONS
# =====================================================


@router.post(
    "/logout-all",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
)
async def logout_all(
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    await service.logout_all(current_user.id)
    return StatusResponse(status="success", message="All sessions revoked")


# =====================================================
# REVOKE ONE SESSION
# =====================================================


@router.delete(
    "/sessions/{session_id}",
    response_model=StatusResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
):
    await service.revoke_session(
        user_id=current_user.id,
        session_id=session_id,
    )
    return StatusResponse(status="success", message="Session revoked")
