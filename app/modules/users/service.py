import os
import uuid
import shutil
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import UploadFile, HTTPException

from app.modules.auth.models import (
    User,
    UserProfile,
    UserContact,
    UserSession
)
from app.modules.users import schemas

class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # =====================================================
    # USER
    # =====================================================

    async def get_user_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def add_premium_subscription(
        self,
        user_id: int,
        days: int
    ) -> User:
        user = await self.get_user_by_id(user_id)
        if not user:
            raise HTTPException(404, "Foydalanuvchi topilmadi")

        now = datetime.now(timezone.utc)

        if user.premium_expires_at and user.premium_expires_at > now:
            user.premium_expires_at = user.premium_expires_at + timedelta(days=days)
        else:
            user.premium_expires_at = now + timedelta(days=days)

        user.is_premium = True

        await self.db.commit()
        await self.db.refresh(user)

        return user

    # =====================================================
    # PROFILE
    # =====================================================

    async def update_profile(
        self,
        user_id: int,
        data: schemas.ProfileUpdate
    ) -> User:

        result = await self.db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()

        update_data = data.model_dump(exclude_unset=True)

        if not profile:
            profile = UserProfile(user_id=user_id, **update_data)
            self.db.add(profile)
        else:
            for field, value in update_data.items():
                setattr(profile, field, value)

        if hasattr(profile, "updated_at"):
            profile.updated_at = datetime.utcnow()

        await self.db.commit()

        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one()

    # =====================================================
    # CONTACTS
    # =====================================================

    async def get_user_contacts(self, user_id: int) -> List[UserContact]:
        result = await self.db.execute(
            select(UserContact)
            .where(UserContact.user_id == user_id)
            .order_by(UserContact.is_primary.desc())
        )
        return list(result.scalars().all())

    async def add_contact_start(
        self,
        user_id: int,
        value: str,
        contact_type: str
    ) -> dict:

        result = await self.db.execute(
            select(UserContact).where(UserContact.value == value)
        )
        existing = result.scalar_one_or_none()

        if existing:
            if existing.user_id != user_id:
                raise HTTPException(400, "Bu kontakt boshqa profilga tegishli")

            if existing.is_verified:
                return {
                    "status": "verified",
                    "message": "Kontakt allaqachon tasdiqlangan"
                }

            return {
                "status": "pending_verification",
                "bot_link": self._generate_bot_link()
            }

        contact = UserContact(
            user_id=user_id,
            contact_type=contact_type,
            value=value,
            is_verified=False,
            is_primary=False
        )

        self.db.add(contact)
        await self.db.commit()

        return {
            "status": "pending_verification",
            "bot_link": self._generate_bot_link()
        }

    async def set_primary_contact(
        self,
        user_id: int,
        contact_id: int
    ) -> dict:

        result = await self.db.execute(
            select(UserContact).where(
                UserContact.id == contact_id,
                UserContact.user_id == user_id
            )
        )
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(404, "Kontakt topilmadi")

        if not contact.is_verified:
            raise HTTPException(400, "Tasdiqlanmagan kontaktni asosiy qilib bo‘lmaydi")

        await self.db.execute(
            update(UserContact)
            .where(
                UserContact.user_id == user_id,
                UserContact.contact_type == contact.contact_type
            )
            .values(is_primary=False)
        )

        contact.is_primary = True

        await self.db.commit()

        return {"message": "Primary kontakt yangilandi"}

    async def delete_contact(
        self,
        user_id: int,
        contact_id: int
    ) -> dict:

        result = await self.db.execute(
            select(UserContact).where(
                UserContact.id == contact_id,
                UserContact.user_id == user_id
            )
        )
        contact = result.scalar_one_or_none()

        if not contact:
            raise HTTPException(404, "Kontakt topilmadi")

        if contact.is_primary:
            raise HTTPException(400, "Asosiy kontaktni o‘chirish mumkin emas")

        await self.db.delete(contact)
        await self.db.commit()

        return {"status": "deleted"}

    # =====================================================
    # AVATAR
    # =====================================================

    async def upload_avatar(
        self,
        user_id: int,
        file: UploadFile
    ) -> str:

        upload_dir = "static/avatars"
        os.makedirs(upload_dir, exist_ok=True)

        ext = os.path.splitext(file.filename or "")[1] or ".jpg"
        filename = f"user_{user_id}_{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(upload_dir, filename)

        try:
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        except Exception:
            raise HTTPException(500, "Faylni saqlashda xatolik")

        avatar_url = f"/static/avatars/{filename}"

        try:
            result = await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()

            if not profile:
                raise HTTPException(404, "Profil topilmadi")

            old_avatar = profile.avatar_url
            profile.avatar_url = avatar_url

            await self.db.commit()

            if old_avatar:
                old_path = old_avatar.lstrip("/")
                if os.path.exists(old_path):
                    os.remove(old_path)

            return avatar_url

        except Exception:
            await self.db.rollback()
            if os.path.exists(file_path):
                os.remove(file_path)
            raise

    # =====================================================
    # SESSIONS
    # =====================================================

    async def get_active_sessions(
        self,
        user_id: int
    ) -> List[UserSession]:

        result = await self.db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_revoked.is_(False)
            )
            .order_by(UserSession.updated_at.desc())
        )

        return list(result.scalars().all())

    async def revoke_session(
        self,
        user_id: int,
        session_id: uuid.UUID
    ) -> dict:

        result = await self.db.execute(
            update(UserSession)
            .where(
                UserSession.id == session_id,
                UserSession.user_id == user_id
            )
            .values(is_revoked=True)
        )

        if result.rowcount == 0:
            raise HTTPException(404, "Session topilmadi")

        await self.db.commit()

        return {"status": "revoked"}

    # =====================================================
    # PRIVATE
    # =====================================================

    def _generate_bot_link(self) -> str:
        return "https://t.me/EnwisAuthBot?start=verify_phone"