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
    async def update_profile(self, user_id: int, data: schemas.ProfileUpdate):
        update_data = data.model_dump(exclude_unset=True)
        if update_data:
            await self.db.execute(update(UserProfile).where(UserProfile.user_id == user_id).values(**update_data))
            await self.db.commit()
        return await self.get_user_by_id(user_id)

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