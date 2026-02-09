from typing import List
import uuid
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.users import schemas
from app.modules.users.service import USERService
from app.modules.auth.models import User
from app.modules.auth.dependencies import get_current_user 

router = APIRouter(prefix="/user/me", tags=["My Profile"])

# --- PROFIL MA'LUMOTLARI ---

@router.get("/", response_model=schemas.UserResponse)
async def get_my_profile(current_user: User = Depends(get_current_user)):
    """Joriy foydalanuvchi ma'lumotlarini olish."""
    return current_user

@router.put("/profile", response_model=schemas.UserResponse)
async def update_profile(
    data: schemas.ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Profil ma'lumotlarini yangilash."""
    service = USERService(db)
    return await service.update_profile(current_user.id, data)

@router.post("/avatar", response_model=schemas.AvatarUpdateResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Profil rasmini yuklash (Avatar)."""
    content_type = getattr(file, "content_type", None)
    if not content_type or not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Faqat rasm yuklash mumkin")
    
    service = USERService(db)
    url = await service.upload_avatar(current_user.id, file)
    return {"avatar_url": url, "message": "Avatar muvaffaqiyatli yuklandi"}

# --- KONTAKTLAR (UserContact) ---

@router.get("/contacts", response_model=List[schemas.UserContactResponse])
async def get_my_contacts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Foydalanuvchining barcha aloqa vositalarini olish."""
    service = USERService(db)
    return await service.get_user_contacts(current_user.id)

@router.post("/phone/update-request")
async def request_phone_update(
    data: schemas.PhoneUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Yangi telefon raqamiga tasdiqlash kodi yuborish."""
    service = USERService(db)
    return await service.update_phone_start(current_user.id, data.new_phone)

@router.post("/phone/verify")
async def verify_phone_update(
    data: schemas.PhoneVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kodni tekshirish va telefon raqamini tasdiqlash."""
    service = USERService(db)
    return await service.update_phone_verify(current_user.id, data)

# --- SESSYALAR (UserSession) ---

@router.get("/sessions", response_model=List[schemas.UserSessionResponse])
async def get_my_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Faol qurilmalar va sessiyalar ro'yxati."""
    service = USERService(db)
    return await service.get_active_sessions(current_user.id)

@router.delete("/sessions/{session_id}")
async def logout_device(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Tanlangan qurilmadagi sessiyani yopish."""
    service = USERService(db)
    await service.revoke_session(current_user.id, session_id)
    return {"message": "Sessiya muvaffaqiyatli yopildi"}