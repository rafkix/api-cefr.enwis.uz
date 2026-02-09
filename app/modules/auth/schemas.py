from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import  Optional
from .models import  VerificationPurpose

# --- TOKENS ---
class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

# --- LOGIN & REGISTER ---
class RegisterRequest(BaseModel):
    full_name: str
    username: str
    email: EmailStr
    phone: str = Field(..., pattern=r"^\+998\d{9}$")
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    login: str  # email yoki username
    password: str

# --- SOCIAL AUTH ---
class GoogleLoginRequest(BaseModel):
    google_id: str
    email: EmailStr
    name: str
    picture: Optional[str] = None

class TelegramLoginRequest(BaseModel):
    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str

# --- PHONE AUTH ---
class SendCodeRequest(BaseModel):
    target: str
    purpose: VerificationPurpose

class PhoneLoginRequest(BaseModel):
    phone: str = Field(..., pattern=r"^\+998\d{9}$")
    code: str = Field(..., min_length=4, max_length=6)

class PhoneRegistrationComplete(BaseModel):
    phone: str
    code: str
    full_name: str
    username: str
    email: Optional[EmailStr] = None

class PhoneAuthResponse(BaseModel):
    status: str  # "success" yoki "need_registration"
    token: Optional[Token] = None
    message: Optional[str] = None
    
class ContactResponse(BaseModel):
    contact_type: str
    value: str
    is_verified: bool
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)

