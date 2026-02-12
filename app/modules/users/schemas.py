import re
import uuid
from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    DEVELOPER = "developer"

class AuthProvider(str, Enum):
    LOCAL = "local"
    GOOGLE = "google"
    TELEGRAM = "telegram"
    ONE_ID = "one_id"

class ContactResponse(BaseModel):
    contact_type: str
    value: str
    is_verified: bool
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)

class ProfileResponse(BaseModel):
    full_name: str
    username: str
    avatar_url: Optional[str] = None
    bio: Optional[str] = None
    birth_date: Optional[datetime] = None
    gender: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

class UserContactResponse(BaseModel):
    id: int
    contact_type: str
    value: str
    is_verified: bool
    is_primary: bool

    class Config:
        from_attributes = True

class UserResponse(BaseModel):
    """Foydalanuvchiga qaytariladigan asosiy ma'lumotlar."""
    id: int
    is_active: bool
    global_role: UserRole
    created_at: datetime
    
    profile: Optional[ProfileResponse] = None
    contacts: List[ContactResponse] = []
    
    model_config = ConfigDict(from_attributes=True)

class UserSessionResponse(BaseModel):
    """ Refresh token sessiyalari ma'lumotlari """
    id: uuid.UUID
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    last_active: datetime = Field(alias="updated_at")
    expires_at: datetime
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

class AvatarUpdateResponse(BaseModel):
    """Rasm yuklanganda qaytariladigan natija"""
    avatar_url: str
    message: str = "Profil rasmi muvaffaqiyatli yangilandi"

    model_config = ConfigDict(from_attributes=True)


class ProfileUpdate(BaseModel):
    """Profil ma'lumotlarini yangilash uchun"""
    full_name: Optional[str] = Field(None, min_length=3, max_length=255)
    username: Optional[str] = Field(None, min_length=3, max_length=100)
    bio: Optional[str] = None
    birth_date: Optional[datetime] = None
    gender: Optional[str] = None

class PasswordChangeRequest(BaseModel):
    """Parolni almashtirish"""
    old_password: str
    new_password: str = Field(..., min_length=8)
    confirm_password: str 

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info):
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Yangi parollar bir-biriga mos kelmadi")
        @field_validator("confirm_password")
        @classmethod
        def passwords_match(cls, value: str, info):
            if "new_password" in info.data and value != info.data["new_password"]:
                raise ValueError("Yangi parollar bir-biriga mos kelmadi")
            return value

class PhoneUpdateRequest(BaseModel):
    """Telefon raqamini yangilash (1-bosqich)"""
    new_phone: str = Field(...)

    @field_validator("new_phone")
    @classmethod
    def validate_phone(cls, value: str):
        if not re.match(r"^\+998\d{9}$", value):
            raise ValueError("Telefon raqami +998XXXXXXXXX formatida bo'lishi shart")
        return value

class PhoneVerifyRequest(BaseModel):
    """Yuborilgan kodni tasdiqlash (2-bosqich)"""
    new_phone: str
    verification_code: str = Field(..., min_length=4, max_length=6)

class SessionRevokeRequest(BaseModel):
    """Sessiyani o'chirish so'rovi"""
    session_id: uuid.UUID

class ContactUpdateRequest(BaseModel):
    """Email yoki boshqa kontaktni yangilash"""
    contact_type: str  # "email", "phone"
    new_value: str
    verification_code: Optional[str] = None

class AddContactRequest(BaseModel):
    value: str # Email yoki Telefon
    type: str  # "phone" yoki "email"
    
class AddContactSchema(BaseModel):
    type: str
    value: str

class AddContactVerify(BaseModel):
    value: str
    code: str
    type: str

class ContactResponse(BaseModel):
    id: int
    value: str
    contact_type: str
    is_primary: bool
    is_verified: bool

    class Config:
        from_attributes = True