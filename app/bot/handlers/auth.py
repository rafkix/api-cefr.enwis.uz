from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError

from app.bot.keyboards.reply import get_contact_keyboard, get_main_keyboard
from app.bot.states.states import AuthFlow
from app.bot.utils.helpers import check_subscription, normalize_phone
from app.core.database import AsyncSessionLocal
from app.modules.auth.models import (
    AuthProvider,
    ContactType,
    User,
    UserContact,
    UserIdentity,
)

router = Router()


async def upsert_user_contact(
    *,
    db,
    user_id: int,
    contact_type: ContactType,
    value: str,
    is_verified: bool = True,
    is_primary: bool = False,
) -> UserContact:
    stmt = select(UserContact).where(
        and_(
            UserContact.user_id == user_id,
            UserContact.contact_type == contact_type,
        )
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.value = value
        existing.is_verified = is_verified
        if is_primary:
            existing.is_primary = True
        return existing

    contact = UserContact(
        user_id=user_id,
        contact_type=contact_type,
        value=value,
        is_verified=is_verified,
        is_primary=is_primary,
    )
    db.add(contact)
    return contact


async def upsert_telegram_identity(*, db, user_id: int, telegram_user_id: int) -> UserIdentity:
    stmt = select(UserIdentity).where(
        and_(
            UserIdentity.user_id == user_id,
            UserIdentity.provider == AuthProvider.TELEGRAM,
        )
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.provider_id = str(telegram_user_id)
        return existing

    identity = UserIdentity(
        user_id=user_id,
        provider=AuthProvider.TELEGRAM,
        provider_id=str(telegram_user_id),
    )
    db.add(identity)
    return identity


@router.message(F.text == "📱 Telefonni tasdiqlash")
async def start_verify_phone(message: types.Message, state: FSMContext):
    if not await check_subscription(message.bot, message.from_user.id):
        return

    await state.set_state(AuthFlow.waiting_contact_verify)
    await message.answer(
        "📱 Telefon raqamingizni tasdiqlash uchun kontaktingizni yuboring:",
        reply_markup=get_contact_keyboard(),
    )


@router.message(AuthFlow.waiting_contact_login, F.contact)
async def process_login_contact(message: types.Message, state: FSMContext):
    if not message.contact:
        return

    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    phone = normalize_phone(message.contact.phone_number)
    tg_id = message.from_user.id

    data = await state.get_data()
    external_user_id = data.get("external_user_id")

    if not external_user_id:
        await state.clear()
        return await message.answer(
            "❌ Tizimda xatolik: sayt foydalanuvchi ID topilmadi. Saytdan qaytadan urinib ko'ring.",
            reply_markup=get_main_keyboard(),
        )

    async with AsyncSessionLocal() as db:
        user = await db.get(User, int(external_user_id))
        if not user:
            await state.clear()
            return await message.answer(
                "❌ Saytdagi foydalanuvchi topilmadi.",
                reply_markup=get_main_keyboard(),
            )

        try:
            await upsert_user_contact(
                db=db,
                user_id=user.id,
                contact_type=ContactType.PHONE,
                value=phone,
                is_verified=True,
                is_primary=True,
            )

            await upsert_user_contact(
                db=db,
                user_id=user.id,
                contact_type=ContactType.TELEGRAM,
                value=str(tg_id),
                is_verified=True,
            )

            await upsert_telegram_identity(
                db=db,
                user_id=user.id,
                telegram_user_id=tg_id,
            )

            await db.commit()

        except IntegrityError:
            await db.rollback()
            return await message.answer(
                "❌ Bu telefon yoki Telegram akkaunt boshqa foydalanuvchiga biriktirilgan.",
                reply_markup=get_main_keyboard(),
            )

    await state.clear()
    await message.answer(
        f"✅ <b>Muvaffaqiyatli bog'landi!</b>\n\n"
        f"📱 Raqam: <code>{phone}</code>\n"
        f"🆔 Telegram ID: <code>{tg_id}</code>\n\n"
        f"Endi saytga qaytib sahifani yangilang.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


@router.message(AuthFlow.waiting_contact_verify, F.contact)
async def process_verify_contact(message: types.Message, state: FSMContext):
    if not message.contact:
        return

    if message.contact.user_id != message.from_user.id:
        return await message.answer("❌ Faqat o'z kontaktingizni yuboring.")

    contact_phone = normalize_phone(message.contact.phone_number)
    tg_id = message.from_user.id

    async with AsyncSessionLocal() as db:
        stmt_phone = select(UserContact).where(
            and_(
                UserContact.contact_type == ContactType.PHONE,
                UserContact.value == contact_phone,
            )
        )
        db_phone_contact = (await db.execute(stmt_phone)).scalar_one_or_none()

        if not db_phone_contact:
            return await message.answer(
                "❌ Bu telefon raqami tizimda topilmadi.\n"
                "Avval saytda ro'yxatdan o'ting."
            )

        try:
            db_phone_contact.is_verified = True
            user_id = db_phone_contact.user_id

            await upsert_user_contact(
                db=db,
                user_id=user_id,
                contact_type=ContactType.TELEGRAM,
                value=str(tg_id),
                is_verified=True,
            )

            await upsert_telegram_identity(
                db=db,
                user_id=user_id,
                telegram_user_id=tg_id,
            )

            await db.commit()

        except IntegrityError:
            await db.rollback()
            return await message.answer(
                "❌ Bu Telegram akkaunt boshqa foydalanuvchiga biriktirilgan.",
                reply_markup=get_main_keyboard(),
            )
        except Exception:
            await db.rollback()
            return await message.answer(
                "❌ Xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.",
                reply_markup=get_main_keyboard(),
            )

    await state.clear()
    await message.answer(
        "✅ <b>Tabriklaymiz! Profilingiz tasdiqlandi.</b>\n\n"
        "Endi saytda barcha imkoniyatlardan foydalanishingiz mumkin.",
        parse_mode="HTML",
        reply_markup=get_main_keyboard(),
    )


@router.message(F.text == "👤 Profilim")
async def my_profile(message: types.Message):
    async with AsyncSessionLocal() as db:
        stmt = select(UserIdentity).where(
            and_(
                UserIdentity.provider == AuthProvider.TELEGRAM,
                UserIdentity.provider_id == str(message.from_user.id),
            )
        )
        identity = (await db.execute(stmt)).scalar_one_or_none()

        if not identity:
            return await message.answer(
                "❌ Sizning Telegram profilingiz hali sayt akkauntiga ulanmagan.",
                reply_markup=get_main_keyboard(),
            )

        user = await db.get(User, identity.user_id)
        if not user:
            return await message.answer("❌ Foydalanuvchi topilmadi.")

        contacts_stmt = select(UserContact).where(UserContact.user_id == user.id)
        contacts = (await db.execute(contacts_stmt)).scalars().all()

        phone = next((c.value for c in contacts if c.contact_type == ContactType.PHONE), "yo'q")
        phone_verified = next(
            (c.is_verified for c in contacts if c.contact_type == ContactType.PHONE),
            False,
        )

        await message.answer(
            f"👤 <b>Profil ma'lumotlari</b>\n\n"
            f"🆔 User ID: <code>{user.id}</code>\n"
            f"📱 Telefon: <code>{phone}</code>\n"
            f"✅ Telefon tasdiqlangan: <b>{'Ha' if phone_verified else 'Yo‘q'}</b>\n"
            f"📊 Status: <b>{'Faol' if user.is_active else 'Bloklangan'}</b>\n"
            f"🎭 Role: <b>{user.global_role.value}</b>",
            parse_mode="HTML",
            reply_markup=get_main_keyboard(),
        )