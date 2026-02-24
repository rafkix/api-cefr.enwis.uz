import requests
import random
import os
from datetime import datetime, timedelta


class OtpService:
    LOGIN_EMAIL = os.environ.get("ESKIZ_EMAIL", "kholikulovelyor@gmail.com")
    LOGIN_PASSWORD = os.environ.get("ESKIZ_PASSWORD", "lWMS8DpghTyKoxHalY8Rvi8OocKFLxYx4pWBSL9f")

    LOGIN_URL = "https://notify.eskiz.uz/api/auth/login"
    SMS_URL = "https://notify.eskiz.uz/api/message/sms/send"

    FROM = "4546"   # Agar ishlamasa dashboarddan tekshir

    _token = None
    _token_expires_at = None

    # =====================================================
    # OTP GENERATION
    # =====================================================

    @staticmethod
    def _generate_otp():
        return str(random.randint(100000, 999999))

    # =====================================================
    # TOKEN
    # =====================================================

    @classmethod
    def _get_token(cls):

        if cls._token and cls._token_expires_at and cls._token_expires_at > datetime.utcnow():
            return cls._token

        response = requests.post(
            cls.LOGIN_URL,
            data={
                "email": cls.LOGIN_EMAIL,
                "password": cls.LOGIN_PASSWORD,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )

        print("LOGIN STATUS:", response.status_code)
        print("LOGIN RESPONSE:", response.text)

        response.raise_for_status()

        data = response.json()

        token = data.get("data", {}).get("token")

        if not token:
            raise Exception("Token topilmadi")

        cls._token = token
        cls._token_expires_at = datetime.utcnow() + timedelta(hours=23)

        print("✅ Token yangilandi")

        return cls._token

    # =====================================================
    # SEND OTP
    # =====================================================

    @classmethod
    def send_otp(cls, phone: str):

        # telefonni string qilish
        phone = str(phone).strip()

        # oddiy validation
        if not phone.isdigit() or not phone.startswith("998") or len(phone) != 12:
            raise ValueError("Telefon formati noto‘g‘ri. Masalan: 998901234567")

        otp = cls._generate_otp()
        token = cls._get_token()
        sender = 'Healthy project'

        message = f"""NarxNav sayti orqali ro\'yxatdan o\'tish uchun tasdiqlash kodingiz: {otp}"""

        # 160 belgidan oshmasin
        if len(message) > 160:
            raise ValueError("SMS 160 belgidan oshdi")

        payload = {
            "mobile_phone": phone,
            "message": message,
            "from": "4546",
        }

        headers = {
            "Authorization": f"Bearer {token}",
        }

        response = requests.post(
            cls.SMS_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )

        print("SMS STATUS:", response.status_code)
        print("SMS RESPONSE:", response.text)

        if response.status_code != 200:
            raise Exception(f"SMS xato: {response.text}")

        print(f"✅ OTP {otp} yuborildi → {phone}")

        return otp


# =====================================================
# RUN
# =====================================================

if __name__ == "__main__":
    phone_number = "998885420818"   # test
    otp = OtpService.send_otp(phone_number)
    print("Yuborilgan OTP:", otp)