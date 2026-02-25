import jwt
import uuid
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from passlib.context import CryptContext
from app.core.config import settings
from typing import Optional, Dict, Any

# Argon2id - eng yuqori xavfsizlik standarti
pwd_context = CryptContext(
    schemes=["argon2"],
    argon2__time_cost=2,      # Ikkita pastki chiziq (__) ishlatiladi
    argon2__memory_cost=102400,
    deprecated="auto"
)

# KONSTANTALAR - Domen cheklovlari uchun
DOMAIN = "enwis.uz"
ISSUER = f"auth.{DOMAIN}"        # Tokenni kim berdi
AUDIENCE = [f"api.{DOMAIN}", f"app.{DOMAIN}",f"cefr.{DOMAIN}", DOMAIN] # Token kimlar uchun


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)
# =====================
# JWT TOKENS (DOMAIN-LOCKED)
# =====================

def create_access_token(user_id: int, extra_data: Optional[Dict[str, Any]] = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "iss": ISSUER,                 # Faqat auth.enwis.uz tomonidan
        "sub": str(user_id),           # User ID
        "aud": AUDIENCE,               # Faqat enwis.uz ekotizimi uchun
        "iat": now,
        "nbf": now,
        "jti": str(uuid.uuid4()),      # Replay attackga qarshi unikal ID
        "type": "access",
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    }
    
    if extra_data:
        payload.update(extra_data)
        
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str, token_type: str) -> dict:
    """
    Tokenni dekod qilishda issuer va audience'ni qat'iy tekshiradi.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            audience=AUDIENCE,         # Audience tekshiruvi (enwis.uz)
            issuer=ISSUER,             # Issuer tekshiruvi (auth.enwis.uz)
            options={
                "verify_exp": True, 
                "verify_iat": True, 
                "verify_nbf": True,
                "require": ["exp", "iat", "iss", "sub", "aud"] # Bu maydonlar bo'lishi shart
            }
        )

        if payload.get("type") != token_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Token turi noto‘g‘ri"
            )

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token muddati tugagan")
    except jwt.InvalidAudienceError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Ushbu token enwis.uz uchun emas!")
    except jwt.InvalidIssuerError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Noma'lum manbadan kelgan token!")
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Token yaroqsiz")