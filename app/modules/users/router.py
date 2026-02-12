from fastapi import APIRouter, Depends, UploadFile, File, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
import uuid

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User
from app.modules.users.service import USERService  # Klas nomi service.py ichida qanday bo'lsa shunday yozing
from app.modules.users import schemas

router = APIRouter(prefix="/user/me", tags=["My Profile"])

# --- DEPENDENCY ---

async def get_service(db: AsyncSession = Depends(get_db)) -> USERService:
    """UserService obyektini yaratish."""
    return USERService(db)

# --- SECTION: PROFILE ---

@router.get("/", response_model=schemas.UserResponse)
async def read_my_profile(user: User = Depends(get_current_user)):
    """Profil ma'lumotlarini olish."""
    return user

@router.put("/profile", response_model=schemas.UserResponse)
async def update_my_profile(
    data: schemas.ProfileUpdate,
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Profilni tahrirlash (ism, bio, va h.k.)."""
    return await service.update_profile(user.id, data)

@router.post("/avatar", response_model=schemas.AvatarUpdateResponse)
async def create_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Profil rasmini yuklash (Maks 10MB)."""
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Faqat rasm yuklash mumkin")
    return {"avatar_url": await service.upload_avatar(user.id, file)}

# --- SECTION: CONTACTS ---

@router.post("/contacts")
async def add_contact_start_api(
    payload: schemas.AddContactSchema, 
    user: User = Depends(get_current_user), 
    service: USERService = Depends(get_service)
):
    """Kontakt qo'shishni boshlash (OTP kod yaratish)."""
    return await service.add_contact_start(
        user_id=user.id, 
        value=payload.value, 
        contact_type=payload.type
    )

@router.post("/contacts/verify")
async def verify_contact_creation(
    data: schemas.AddContactVerify,
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """OTPni tasdiqlash va kontaktni saqlash."""
    return await service.add_contact_verify(
        user_id=user.id, 
        value=data.value, 
        code=data.code, 
        contact_type=data.type
    )

@router.get("/contacts", response_model=List[schemas.ContactResponse])
async def read_my_contacts(
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Barcha kontaktlar ro'yxati."""
    return await service.get_user_contacts(user.id)

@router.patch("/contacts/{contact_id}/primary")
async def update_contact_primary_status(
    contact_id: int,
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Kontaktni asosiy (primary) qilish."""
    return await service.set_primary_contact(user.id, contact_id)

@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_contact(
    contact_id: int,
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Kontaktni o'chirish."""
    await service.delete_contact(user.id, contact_id)

# --- SECTION: SESSIONS ---

@router.get("/sessions", response_model=List[schemas.UserSessionResponse])
async def read_active_sessions(
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Faol qurilmalar ro'yxati."""
    return await service.get_active_sessions(user.id)

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    service: USERService = Depends(get_service)
):
    """Sessiyani yopish."""
    return await service.revoke_session(user.id, session_id)