from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from datetime import datetime
from typing import List

# Tashqi Result modellarni import qilish (MUHIM!)
from app.modules.services.exams.listening.models import ListeningExam, ListeningResult
from app.modules.services.exams.reading.models import ReadingTest, ReadingResult
from app.modules.services.exams.writing.models import WritingExam, WritingResult

from .models import (
    MockExam, MockExamAttempt, MockPurchase, MockSkillAttempt,
    MockExamResult, SkillType
)
from .schemas import MockExamCreate, MockExamUpdate, MockSkillSubmit

# --- 1. DTM STANDARTLASHTIRISH VA BAHOLASH LOGIKASI ---
def calculate_scaled_score(raw_score: float, skill: SkillType) -> float:
    if skill in [SkillType.READING, SkillType.LISTENING]:
        if raw_score >= 28: return round(65.0 + (raw_score - 28) * (10 / 7), 1)
        elif raw_score >= 18: return round(51.0 + (raw_score - 18) * (13 / 9), 1)
        elif raw_score >= 10: return round(38.0 + (raw_score - 10) * (12 / 7), 1)
        else: return round(raw_score * 3.8, 1)
    return min(raw_score, 75.0)

def get_cefr_level(score: float) -> str:
    if score >= 65: return "C1"
    if score >= 51: return "B2"
    if score >= 38: return "B1"
    return "B1 dan quyi"
# --- 2. CORE CRUD SERVICES (Admin uchun) ---
async def create_exam(db: AsyncSession, data: MockExamCreate) -> MockExam:
    """Yangi imtihon yaratish va testlarni avtomatik tanlash."""

    # --- 1. Reading ID ni aniqlash ---
    if data.reading_id:
        r_id = data.reading_id
    else:
        r_stmt = select(ReadingTest.id).where(
            ReadingTest.is_mock == True, 
            ReadingTest.cefr_level == data.cefr_level
        ).order_by(ReadingTest.created_at.desc()).limit(1)
        r_id = (await db.execute(r_stmt)).scalar_one_or_none()
        if not r_id:
            raise HTTPException(400, f"Bazada {data.cefr_level} darajali Mock Reading testi mavjud emas. Avval test yarating.")

    # --- 2. Listening ID ni aniqlash ---
    if data.listening_id:
        l_id = data.listening_id
    else:
        l_stmt = select(ListeningExam.id).where(
            ListeningExam.is_mock == True, 
            ListeningExam.cefr_level == data.cefr_level
        ).order_by(ListeningExam.created_at.desc()).limit(1)
        l_id = (await db.execute(l_stmt)).scalar_one_or_none()
        if not l_id:
            raise HTTPException(400, f"Bazada {data.cefr_level} darajali Mock Listening testi mavjud emas. Avval test yarating.")
        
    if data.writing_id:
        w_id = data.writing_id
    else:
        w_stmt = select(WritingExam.id).where(
            WritingExam.is_mock == True,
            WritingExam.cefr_level == data.cefr_level
        ).order_by(WritingExam.created_at.desc()).limit(1)
        w_id = (await db.execute(w_stmt)).scalar_one_or_none()
        if not w_id:
            raise HTTPException(400, f"Bazada {data.cefr_level} darajali Mock Listening testi mavjud emas. Avval test yarating.")

    # --- 3. Exam yaratish ---
    new_exam = MockExam(
        **data.model_dump(exclude={"reading_id", "listening_id", "writing_id"}),
        reading_id=r_id,
        listening_id=l_id,
        writing_id=w_id
        
    )
    db.add(new_exam)
    await db.commit()
    await db.refresh(new_exam)
    return new_exam


async def get_all_exams_admin(db: AsyncSession) -> List[MockExam]:
    stmt = select(MockExam).order_by(MockExam.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())

async def update_exam(db: AsyncSession, exam_id: str, data: MockExamUpdate) -> MockExam:
    exam = await db.get(MockExam, exam_id)
    if not exam:
        raise HTTPException(404, "Imtihon topilmadi")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(exam, key, value)
    await db.commit()
    await db.refresh(exam)
    return exam

async def delete_exam_service(db: AsyncSession, exam_id: str):
    exam = await db.get(MockExam, exam_id)
    if not exam:
        raise HTTPException(404, "Imtihon topilmadi")
    await db.delete(exam)
    await db.commit()

# --- 3. PURCHASE & ACCESS SERVICES ---
async def list_user_exams(db: AsyncSession, user_id: int) -> List[dict]:
    exams = (await db.execute(select(MockExam).where(MockExam.is_active == True))).scalars().all()
    purchase_stmt = select(MockPurchase.mock_exam_id).where(
        and_(MockPurchase.user_id == user_id, MockPurchase.is_active == True)
    )
    purchased_ids = set((await db.execute(purchase_stmt)).scalars().all())

    return [{
        "id": e.id,
        "title": e.title,
        "cefr_level": e.cefr_level,
        "price": e.price,
        "is_active": e.is_active,
        "is_purchased": e.id in purchased_ids,
        "reading_id": e.reading_id,
        "listening_id": e.listening_id,
        "writing_id": e.writing_id,
        "speaking_id": e.speaking_id,
        "created_at": e.created_at
    } for e in exams]

async def buy_exam_request(db: AsyncSession, user_id: int, exam_id: str):
    check_stmt = select(MockPurchase).where(
        and_(MockPurchase.user_id == user_id, MockPurchase.mock_exam_id == exam_id)
    )
    if (await db.execute(check_stmt)).scalar_one_or_none():
        raise HTTPException(400, "Sizda ushbu imtihon uchun allaqachon so'rov mavjud.")
    
    purchase = MockPurchase(user_id=user_id, mock_exam_id=exam_id, is_active=False)
    db.add(purchase)
    await db.commit()
    return purchase

# --- 4. EXAM PROCESS SERVICES ---
async def start_exam(db: AsyncSession, user_id: int, exam_id: str) -> MockExamAttempt:
    # 1. Yangi urinishni (attempt) yaratish
    attempt = MockExamAttempt(user_id=user_id, mock_exam_id=exam_id)
    db.add(attempt)
    await db.flush() # ID ni olish uchun
    
    # 2. Har bir bo'lim uchun bo'sh urinishlarni yaratish
    for skill_type in SkillType:
        new_skill = MockSkillAttempt(
            attempt_id=attempt.id,
            user_id=user_id,
            skill=skill_type,
            is_checked=False,
            submitted_at=None,
            raw_score=0,
            scaled_score=0.0
        )
        db.add(new_skill)
        
    await db.commit()
    await db.refresh(attempt)
    return attempt

async def get_attempt_status_service(db: AsyncSession, attempt_id: int):
    ALL_SKILLS = ["LISTENING", "READING", "WRITING", "SPEAKING"]

    stmt = select(MockSkillAttempt).where(MockSkillAttempt.attempt_id == attempt_id)
    res = await db.execute(stmt)
    db_skills = res.scalars().all()
    skill_map = {s.skill.upper(): s for s in db_skills}

    result = []
    for skill in ALL_SKILLS:
        s = skill_map.get(skill)
        # s.submitted_at mavjudligi bo'lim topshirilganini bildiradi
        is_submitted = True if (s and s.submitted_at is not None) else False
        
        result.append({
            "skill": skill,
            "is_checked": bool(s and s.is_checked),
            "is_submitted": is_submitted,
            "submitted_at": s.submitted_at if s else None
        })
    return result


async def submit_skill(db: AsyncSession, attempt_id: int, skill: SkillType, user_id: int):
    """
    Foydalanuvchi biror bo'limni (masalan, Reading) tugatganini bildiradi.
    Funksiya tegishli modul jadvalidan natijani oladi va Mock statusini yangilaydi.
    """
    # 1. Bo'lim urinishini qidirish
    stmt = select(MockSkillAttempt).where(
        and_(
            MockSkillAttempt.attempt_id == attempt_id,
            MockSkillAttempt.skill == skill
        )
    )
    result = await db.execute(stmt)
    skill_attempt = result.scalar_one_or_none()

    if not skill_attempt:
        raise HTTPException(status_code=404, detail="Bo'lim urinishi topilmadi")
    
    if skill_attempt.submitted_at is not None:
        raise HTTPException(status_code=400, detail="Ushbu bo'lim allaqachon topshirilgan")

    # 2. MockAttempt orqali tegishli test ID sini aniqlash
    # (Sessiyaga bog'langan MockExam dan ID larni olamiz)
    attempt_stmt = select(MockExamAttempt).options(selectinload(MockExamAttempt.exam)).where(MockExamAttempt.id == attempt_id)
    attempt_data = (await db.execute(attempt_stmt)).scalar_one_or_none()
    exam = attempt_data.exam

    # 3. Tegishli modul natijalar jadvalidan ballni tortib olish
    raw_score = 0.0
    if skill == SkillType.READING:
        r_res = await db.execute(select(ReadingResult.score).where(
            and_(ReadingResult.test_id == exam.reading_id, ReadingResult.user_id == user_id)
        ).order_by(ReadingResult.created_at.desc()))
        raw_score = r_res.scalar_one_or_none() or 0.0
        
    elif skill == SkillType.LISTENING:
        l_res = await db.execute(select(ListeningResult.score).where(
            and_(ListeningResult.exam_id == exam.listening_id, ListeningResult.user_id == user_id)
        ).order_by(ListeningResult.created_at.desc()))
        raw_score = l_res.scalar_one_or_none() or 0.0

    # 4. MockSkillAttempt jadvalini yangilash
    skill_attempt.submitted_at = datetime.utcnow()
    skill_attempt.raw_score = raw_score

    if skill in [SkillType.READING, SkillType.LISTENING]:
        # Avtomatik hisoblash
        skill_attempt.scaled_score = calculate_scaled_score(raw_score, skill)
        skill_attempt.cefr_level = get_cefr_level(skill_attempt.scaled_score)
        skill_attempt.is_checked = True 
    else:
        # Writing va Speaking (admin tekshiruvi kutiladi)
        # WritingResult balli keyinroq finish_exam_service da yig'iladi
        skill_attempt.scaled_score = 0.0 
        skill_attempt.is_checked = False 

    try:
        await db.commit()
        await db.refresh(skill_attempt)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Xatolik yuz berdi")
    
    return skill_attempt

async def finish_exam_service(db: AsyncSession, attempt_id: int) -> MockExamResult:
    # 1. Attempt yuklash
    stmt = select(MockExamAttempt).options(selectinload(MockExamAttempt.exam)).where(MockExamAttempt.id == attempt_id)
    result = await db.execute(stmt)
    attempt = result.scalar_one_or_none()

    if not attempt: raise HTTPException(404, "Sessiya topilmadi")
    if attempt.is_finished:
        res_stmt = select(MockExamResult).where(MockExamResult.attempt_id == attempt_id)
        return (await db.execute(res_stmt)).scalar_one_or_none()

    user_id = attempt.user_id
    exam = attempt.exam

    # 2. Modullardan natijalarni yig'ish
    # Reading
    r_stmt = select(ReadingResult.score).where(and_(ReadingResult.test_id == exam.reading_id, ReadingResult.user_id == user_id)).order_by(ReadingResult.created_at.desc())
    reading_raw = (await db.execute(r_stmt)).scalar_one_or_none() or 0.0

    # Listening
    l_stmt = select(ListeningResult.score).where(and_(ListeningResult.exam_id == exam.listening_id, ListeningResult.user_id == user_id)).order_by(ListeningResult.created_at.desc())
    listening_raw = (await db.execute(l_stmt)).scalar_one_or_none() or 0.0

    # Writing (WritingResult dan overall_score olinadi)
    w_stmt = select(WritingResult.overall_score).where(and_(WritingResult.exam_id == exam.writing_id, WritingResult.user_id == user_id)).order_by(WritingResult.created_at.desc())
    writing_score = (await db.execute(w_stmt)).scalar_one_or_none() or 0.0

    # 3. Scaled Ballar
    s_reading = calculate_scaled_score(reading_raw, SkillType.READING)
    s_listening = calculate_scaled_score(listening_raw, SkillType.LISTENING)
    s_speaking = 0.0 # Kelajakda qo'shish uchun

    # 4. Final Average (4 ga bo'lish)
    avg_score = round((s_reading + s_listening + writing_score + s_speaking) / 4, 1)

    # 5. Saqlash
    exam_result = MockExamResult(
        attempt_id=attempt.id,
        user_id=user_id,
        reading_ball=s_reading,
        listening_ball=s_listening,
        writing_ball=writing_score,
        speaking_ball=s_speaking,
        overall_score=avg_score,
        cefr_level=get_cefr_level(avg_score) # TUZATILDI
    )

    attempt.is_finished = True
    attempt.finished_at = datetime.utcnow()
    
    db.add(exam_result)
    await db.commit()
    await db.refresh(exam_result)
    return exam_result

async def get_user_results_history(db: AsyncSession, user_id: int) -> List[MockExamResult]:
    stmt = select(MockExamResult).where(MockExamResult.user_id == user_id).order_by(MockExamResult.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()

async def get_mock_result_service(db: AsyncSession, attempt_id: int) -> MockExamResult:
    stmt = select(MockExamResult).where(MockExamResult.attempt_id == attempt_id)
    result = (await db.execute(stmt)).scalar_one_or_none()
    if not result:
        raise HTTPException(404, "Ushbu imtihon uchun natija hali mavjud emas.")
    return result
