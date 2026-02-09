import os
import uuid
import shutil
from typing import List, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException

from app.modules.auth.models import User, UserProfile, UserContact, UserSession
from app.modules.users import schemas

class USERService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        """Foydalanuvchini ID orqali olish (Read-only)"""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: int, data: schemas.ProfileUpdate) -> User:
        """Profil ma'lumotlarini yangilash"""
        update_data = data.model_dump(exclude_unset=True)
        
        if update_data:
            try:
                query = (
                    update(UserProfile)
                    .where(UserProfile.user_id == user_id)
                    .values(**update_data)
                )
                await self.db.execute(query)
                await self.db.flush()  # Bazaga yuborish
                await self.db.commit() # Tranzaksiyani yopish
            except Exception as e:
                await self.db.rollback()
                raise HTTPException(status_code=500, detail=f"Profilni yangilashda xatolik: {str(e)}")

        return await self.get_user_by_id(user_id)

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

    async def update_phone_start(self, user_id: int, new_phone: str):
        """Telefonni o'zgartirish: 1-bosqich (SMS yuborish)"""
        # Bu yerda SMS xizmati ulanadi (masalan Eskiz.uz)
        # Hozircha kod: 123456
        return {"message": "Tasdiqlash kodi yangi raqamga yuborildi", "debug_code": "123456"}

    async def update_phone_verify(self, user_id: int, data: schemas.PhoneVerifyRequest):
        """Telefonni o'zgartirish: 2-bosqich (Kodni tekshirish va saqlash)"""
        # Test uchun kodni tekshirish
        if data.verification_code != "123456":
            raise HTTPException(status_code=400, detail="Tasdiqlash kodi noto'g'ri")

        try:
            # 1. Eski primary raqamlarni oddiy holatga o'tkazish
            await self.db.execute(
                update(UserContact)
                .where(UserContact.user_id == user_id, UserContact.contact_type == "phone")
                .values(is_primary=False)
            )

            # 2. Yangi raqam allaqachon bo'lsa uni o'chirish (duplicate error oldini olish)
            await self.db.execute(
                delete(UserContact)
                .where(UserContact.user_id == user_id, UserContact.value == data.new_phone)
            )

            # 3. Yangi raqamni qo'shish
            new_contact = UserContact(
                user_id=user_id,
                contact_type="phone",
                value=data.new_phone,
                is_verified=True,
                is_primary=True
            )
            self.db.add(new_contact)
            
            await self.db.flush()
            await self.db.commit()
            return {"message": "Telefon raqami muvaffaqiyatli yangilandi"}
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="Bazaga yozishda xatolik yuz berdi")

    async def get_user_contacts(self, user_id: int) -> List[UserContact]:
        """Foydalanuvchining barcha kontaktlarini olish"""
        result = await self.db.execute(
            select(UserContact)
            .where(UserContact.user_id == user_id)
            .order_by(UserContact.is_primary.desc())
        )
        return list(result.scalars().all())

    async def get_active_sessions(self, user_id: int) -> List[UserSession]:
        """Faqat faol sessiyalarni olish"""
        result = await self.db.execute(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.is_revoked == False)
            # last_active o'rniga created_at yoki modelingizdagi bor ustunni yozing
            .order_by(UserSession.created_at.desc()) 
        )
        return list(result.scalars().all())

    async def revoke_session(self, user_id: int, session_id: uuid.UUID):
        """Sessiyani yopish"""
        try:
            await self.db.execute(
                update(UserSession)
                .where(UserSession.id == session_id, UserSession.user_id == user_id)
                .values(is_revoked=True)
            )
            await self.db.flush()
            await self.db.commit()
            return {"status": "success"}
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail="Sessiyani tugatib bo'lmadi")