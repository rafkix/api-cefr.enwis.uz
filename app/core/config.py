from typing import List, Optional, Any
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Enwis Cefr Backecnd"
    DATABASE_URL: str = "sqlite+aiosqlite:///./enwis.db"
    
    SECRET_KEY: str = "CHANGE_ME_PLEASE_REPLACE"
    ALGORITHM: str = "HS256"
    AUDIENCE: str = "enwis_auth"
    
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_BOT_USERNAME: str = "EnwisAuthBot"
    
    # Muhim: Pydantic JSON deb xato o'ylamasligi uchun Any yoki Union ishlatamiz
    ALLOWED_ORIGINS: Any = [
        "https://app.enwis.uz",
        "https://cefr.enwis.uz",
        "https://ielts.enwis.uz"
    ]
    
    ACCESS_TOKEN_MINUTES: int = 60
    REFRESH_TOKEN_DAYS: int = 30
    COOKIE_DOMAIN: Optional[str] = ".enwis.uz"
    COOKIE_SECURE: bool = True
    COOKIE_HTTPONLY: bool = True
    COOKIE_DOMAIN: Optional[str] = ".enwis.uz"
    INTERNAL_API_TOKEN: str = "CHANGE_ME_INTERNAL_TOKEN"
    

    model_config = SettingsConfigDict(
        env_file=".env", 
        env_file_encoding="utf-8", 
        case_sensitive=False,
        extra="ignore"
    )

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return []

settings = Settings()