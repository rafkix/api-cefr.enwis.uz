import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional

import requests


logger = logging.getLogger(__name__)


class SmsService:
    LOGIN_URL = "https://notify.eskiz.uz/api/auth/login"
    SMS_URL = "https://notify.eskiz.uz/api/message/sms/send"

    FROM = os.environ.get("ESKIZ_FROM", "4546")

    _token: Optional[str] = None
    _token_expires_at: Optional[datetime] = None

    @classmethod
    def _get_credentials(cls) -> tuple[str, str]:
        email = os.environ.get("ESKIZ_EMAIL")
        password = os.environ.get("ESKIZ_PASSWORD")

        if not email or not password:
            raise RuntimeError("ESKIZ_EMAIL yoki ESKIZ_PASSWORD topilmadi")

        return email, password

    @staticmethod
    def normalize_phone(phone: str) -> str:
        value = str(phone).strip()

        if value.startswith("+"):
            value = value[1:]

        value = re.sub(r"\D", "", value)

        if not value.startswith("998") or len(value) != 12:
            raise ValueError("Telefon formati noto‘g‘ri. Masalan: 998901234567")

        return value

    @classmethod
    def _get_token(cls) -> str:
        now = datetime.utcnow()

        if cls._token and cls._token_expires_at and cls._token_expires_at > now:
            return cls._token

        email, password = cls._get_credentials()

        try:
            response = requests.post(
                cls.LOGIN_URL,
                data={
                    "email": email,
                    "password": password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.exception("Eskiz login request failed")
            raise RuntimeError("SMS provider auth xatosi") from e

        try:
            data = response.json()
        except ValueError as e:
            logger.exception("Eskiz login response is not valid JSON")
            raise RuntimeError("SMS provider noto‘g‘ri javob qaytardi") from e

        token = data.get("data", {}).get("token")
        if not token:
            logger.error("Eskiz token not found in response: %s", data)
            raise RuntimeError("SMS provider token qaytarmadi")

        cls._token = token
        cls._token_expires_at = now + timedelta(hours=23)

        logger.info("Eskiz token refreshed")
        return token

    @classmethod
    def send_sms(cls, phone: str, message: str) -> dict:
        normalized_phone = cls.normalize_phone(phone)

        if not message or not message.strip():
            raise ValueError("SMS matni bo‘sh bo‘lishi mumkin emas")

        message = message.strip()

        if len(message) > 160:
            raise ValueError("SMS 160 belgidan oshmasligi kerak")

        token = cls._get_token()

        payload = {
            "mobile_phone": normalized_phone,
            "message": message,
            "from": cls.FROM,
        }

        headers = {
            "Authorization": f"Bearer {token}",
        }

        try:
            response = requests.post(
                cls.SMS_URL,
                json=payload,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.exception("Eskiz SMS send request failed")
            raise RuntimeError("SMS yuborishda xatolik yuz berdi") from e

        try:
            data = response.json()
        except ValueError as e:
            logger.exception("Eskiz SMS response is not valid JSON")
            raise RuntimeError("SMS provider noto‘g‘ri javob qaytardi") from e

        # Provider contractga qarab bu checkni keyin aniqroq qilasan
        # Hozir hech bo‘lmasa JSON body'ni qaytaramiz/loglaymiz.
        logger.info("SMS sent to %s", normalized_phone)
        return data

    @classmethod
    def send_otp(cls, phone: str, otp: str) -> dict:
        message = f"NarxNav sayti orqali ro\'yxatdan o\'tish uchun tasdiqlash kodingiz: {otp}"
        return cls.send_sms(phone=phone, message=message)