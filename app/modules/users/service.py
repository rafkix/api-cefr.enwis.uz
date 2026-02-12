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

    # --- CREATE (Contact & Avatar) ---
    # Backend (API qismi)
    async def add_contact_start(self, user_id: int, value: str, contact_type: str):
        # 1. Avval mavjudligini tekshirish
        existing = await self.db.execute(select(UserContact).where(UserContact.value == value))
        if existing.scalar_one_or_none():
            # Bu yerda detail='...' deb yuboring, FastAPI detail kutadi
            raise HTTPException(400, detail="Bu kontakt allaqachon mavjud")

        code = str(secrets.randbelow(900000) + 100000)
        
        # Eskilarini o'chirish
        await self.db.execute(delete(VerificationCode).where(VerificationCode.target == value))
        
        # Yangi kodni saqlash
        self.db.add(VerificationCode(
            target=value, 
            code=code, 
            purpose=VerificationPurpose.ADD_CONTACT,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10)
        ))
        
        await self.db.commit()
        # Frontendda toast ko'rinishi uchun
        return {"status": "success", "message": "Kod yuborildi"}

    async def add_contact_verify(self, user_id: int, value: str, code: str, contact_type: str):
        stmt = select(VerificationCode).where(
            VerificationCode.target == value, VerificationCode.code == code, VerificationCode.is_used == False
        )
        v_code = (await self.db.execute(stmt)).scalar_one_or_none()
        if not v_code or v_code.expires_at < datetime.now(timezone.utc):
            raise HTTPException(400, "Kod xato yoki muddati o'tgan")

        async with self.db.begin_nested():
            new_contact = UserContact(user_id=user_id, contact_type=contact_type, value=value, is_verified=True)
            self.db.add(new_contact)
            v_code.is_used = True
        await self.db.commit()
        return {"message": "Kontakt qo'shildi"}

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