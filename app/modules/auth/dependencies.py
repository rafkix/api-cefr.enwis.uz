from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_token
from app.modules.auth.service import AuthService
from app.modules.auth.models import User, UserRole

# Frontend token yuboradigan URL (Swaggerda login tugmasi paydo bo'lishi uchun)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Har bir himoyalangan endpoint uchun foydalanuvchini tekshirish.
    Tokenni deodkod qiladi va bazadan User obyektini qaytaradi.
    """
    payload = decode_token(token, token_type="access")
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token tarkibida foydalanuvchi ma'lumoti yo'q",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. AuthService orqali foydalanuvchini barcha bog'liqliklari bilan olish
    service = AuthService(db)
    try:
        user = await service._get_user_full(int(user_id))
    except HTTPException:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Foydalanuvchi topilmadi yoki hisob o'chirilgan",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

async def require_admin(current_user: User = Depends(get_current_user)):
    """
    Faqat ADMIN huquqiga ega foydalanuvchilarni o'tkazadi.
    """
    if current_user.global_role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ushbu amalni bajarish uchun sizda yetarli huquqlar mavjud emas (Faqat Admin)."
        )
    return current_user