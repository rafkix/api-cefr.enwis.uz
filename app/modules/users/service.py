import os
import uuid
import shutil
import secrets
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException, status

from app.modules.auth.models import (
    User, UserProfile, UserContact, UserSession, 
    VerificationCode, VerificationPurpose
)
from app.modules.users import schemas

class USERService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # --- READ ---
    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_user_contacts(self, user_id: int) -> List[UserContact]:
        result = await self.db.execute(
            select(UserContact).where(UserContact.user_id == user_id).order_by(UserContact.is_primary.desc())
        )
        return list(result.scalars().all())

    async def get_active_sessions(self, user_id: int) -> List[UserSession]:
        result = await self.db.execute(
            select(UserSession).where(UserSession.user_id == user_id, UserSession.is_revoked == False)
            .order_by(UserSession.updated_at.desc())
        )
        return list(result.scalars().all())


    # --- IMPROVED: No Verification Code, Just Bot Link ---
    async def add_contact_start(self, user_id: int, value: str, contact_type: str):
        # 1. Tekshiramiz: Bu raqam allaqachon biror foydalanuvchida bormi?
        existing = await self.db.execute(
            select(UserContact).where(UserContact.value == value)
        )
        contact = existing.scalar_one_or_none()

        if contact:
            if contact.user_id != user_id:
                # Raqam boshqa odamga tegishli
                raise HTTPException(400, "Bu raqam boshqa profilga biriktirilgan")
            if contact.is_verified:
                # Raqam o'ziga tegishli va allaqachon tasdiqlangan
                return {"message": "Raqam allaqachon tasdiqlangan", "status": "verified"}
        else:
            # 2. Agar raqam bazada bo'lmasa, uni tasdiqlanmagan (is_verified=False) holatda yaratamiz
            new_contact = UserContact(
                user_id=user_id,
                contact_type=contact_type,
                value=value,
                is_verified=False
            )
            self.db.add(new_contact)
            await self.db.commit()

        # 3. Foydalanuvchiga Telegram bot linkini qaytaramiz
        # Agar raqam bazada bo'lsa, shunchaki verify_phone linkini beramiz
        bot_link = "https://t.me/EnwisAuthBot?start=verify_phone"
        
        return {
            "message": "Raqam saqlandi, bot orqali tasdiqlang",
            "bot_link": bot_link,
            "status": "pending_verification"
        }

    # --- UPDATE (Profile & Primary Status) ---
    async def upload_avatar(self, user_id: int, file: UploadFile) -> str:
        """Profil rasmini yuklash va URLni saqlash"""
        upload_dir = "static/avatars"
        os.makedirs(upload_dir, exist_ok=True)

        # Fayl nomini generatsiya qilish
        original_filename = getattr(file, "filename", "") or ""
        _, ext = os.path.splitext(original_filename)
        file_ext = ext.lstrip(".") if ext else "jpg"
        file_name = f"user_{user_id}_{uuid.uuid4().hex}.{file_ext}"
        file_path = os.path.join(upload_dir, file_name)

        # Faylni diskka yozish
        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception as e:
            raise HTTPException(status_code=500, detail="Faylni serverga yozishda xatolik")

        avatar_url = f"/static/avatars/{file_name}"
        
        try:
            # Bazada avatar URLni yangilash
            await self.db.execute(
                update(UserProfile)
                .where(UserProfile.user_id == user_id)
                .values(avatar_url=avatar_url)
            )
            await self.db.flush()
            await self.db.commit()
            return avatar_url
        except Exception as e:
            await self.db.rollback()
            # Agar DBga yozishda xato bo'lsa, yuklangan faylni o'chirib tashlaymiz
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(status_code=500, detail=f"Ma'lumotlar bazasi qulflangan yoki xato: {str(e)}")

    async def set_primary_contact(self, user_id: int, contact_id: int):
        contact = (await self.db.execute(
            select(UserContact).where(UserContact.id == contact_id, UserContact.user_id == user_id)
        )).scalar_one_or_none()
        
        if not contact: raise HTTPException(404, "Kontakt topilmadi")

        await self.db.execute(
            update(UserContact).where(UserContact.user_id == user_id, UserContact.contact_type == contact.contact_type)
            .values(is_primary=False)
        )
        contact.is_primary = True
        await self.db.commit()
        return {"message": "Asosiy kontakt yangilandi"}

    # --- DELETE (Contact & Session) ---
    async def delete_contact(self, user_id: int, contact_id: int):
        contact = (await self.db.execute(
            select(UserContact).where(UserContact.id == contact_id, UserContact.user_id == user_id)
        )).scalar_one_or_none()
        
        if not contact or contact.is_primary:
            raise HTTPException(400, "Asosiy kontaktni o'chirib bo'lmaydi")
        
        await self.db.delete(contact)
        await self.db.commit()
        return {"status": "success"}

    async def revoke_session(self, user_id: int, session_id: uuid.UUID):
        await self.db.execute(
            update(UserSession).where(UserSession.id == session_id, UserSession.user_id == user_id).values(is_revoked=True)
        )
        await self.db.commit()