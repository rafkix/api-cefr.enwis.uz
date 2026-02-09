from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
from fastapi import HTTPException
from datetime import datetime
from typing import List, Optional, Dict

from app.modules.services.exams.listening.models import ListeningExam
from app.modules.services.exams.reading.models import ReadingTest
from .models import (
    MockExam, MockExamAttempt, MockPurchase, MockSkillAttempt,
    MockExamResult, SkillType
)
from .schemas import MockExamCreate, MockExamUpdate, MockSkillSubmit

# --- 1. DTM STANDARTLASHTIRISH VA BAHOLASH LOGIKASI ---
def calculate_scaled_score(raw_score: float, skill: SkillType) -> float:
    """To'g'ri javoblar sonini DTM 75 ballik standart shkalasiga o'tkazish."""
    if skill in [SkillType.READING, SkillType.LISTENING]:
        if raw_score >= 28:  # C1 (28-35 to'g'ri javob)
            return round(65.0 + (raw_score - 28) * (10 / 7), 1)
        elif raw_score >= 18:  # B2 (18-27 to'g'ri javob)
            return round(51.0 + (raw_score - 18) * (13 / 9), 1)
        elif raw_score >= 10:  # B1 (10-17 to'g'ri javob)
            return round(38.0 + (raw_score - 10) * (12 / 7), 1)
        else:  # B1 dan quyi (0-9 to'g'ri javob)
            return round(raw_score * 3.8, 1)
    return min(raw_score, 75.0)

def get_cefr_level(score: float) -> str:
    """Umumiy ball asosida CEFR darajasini aniqlash."""
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

    # --- 3. Exam yaratish ---
    new_exam = MockExam(
        **data.model_dump(exclude={"reading_id", "listening_id"}),
        reading_id=r_id,
        listening_id=l_id
    )
    db.add(new_exam)
    await db.commit()
    await db.refresh(new_exam)
    return new_exam


async def get_all_exams_admin(db: AsyncSession) -> List[MockExam]:
    stmt = select(MockExam).order_by(MockExam.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()

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


async def submit_skill(db: AsyncSession, attempt_id: int, skill: SkillType, data: MockSkillSubmit):
    # 1. Bo'lim urinishini bazadan qidirish
    stmt = select(MockSkillAttempt).where(
        and_(
            MockSkillAttempt.attempt_id == attempt_id,
            MockSkillAttempt.skill == skill
        )
    )
    result = await db.execute(stmt)
    skill_attempt = result.scalar_one_or_none()

    # 2. Xavfsizlik tekshiruvlari
    if not skill_attempt:
        raise HTTPException(status_code=404, detail="Ushbu bo'lim urinishi topilmadi")
    
    # Agar submitted_at allaqachon mavjud bo'lsa, demak topshirib bo'lingan
    if skill_attempt.submitted_at is not None:
        raise HTTPException(status_code=400, detail="Ushbu bo'lim allaqachon topshirilgan")

    # 3. Ma'lumotlarni yangilash
    skill_attempt.raw_score = data.raw_score
    skill_attempt.user_answers = data.user_answers
    # ✅ Qat'iyan topshirish vaqtini belgilaymiz
    skill_attempt.submitted_at = datetime.utcnow()

    # 4. Ballarni hisoblash mantiqi
    if skill in [SkillType.READING, SkillType.LISTENING]:
        # Avtomatik tekshiriladigan bo'limlar
        skill_attempt.scaled_score = calculate_scaled_score(data.raw_score, skill)
        skill_attempt.cefr_level = get_cefr_level(skill_attempt.scaled_score)
        skill_attempt.is_checked = True 
    else:
        # Writing va Speaking uchun (keyinchalik admin tekshirishi uchun)
        skill_attempt.scaled_score = 0.0
        skill_attempt.cefr_level = None
        # Bu yerda is_checked = False qolishi kerak, chunki hali inson tekshirmadi
        skill_attempt.is_checked = False 

    # 5. Bazaga saqlash
    try:
        await db.commit()
        await db.refresh(skill_attempt)
    except Exception as e:
        await db.rollback()
        print(f"Database Error: {e}") # Debug uchun
        raise HTTPException(status_code=500, detail="Ma'lumotni saqlashda xatolik yuz berdi")
    
    return skill_attempt

async def finish_exam_service(db: AsyncSession, attempt_id: int) -> MockExamResult:
    # 1. Attempt va unga tegishli skilllarni yuklab olish
    stmt = select(MockExamAttempt).options(
        selectinload(MockExamAttempt.skills)
    ).where(MockExamAttempt.id == attempt_id)
    
    result = await db.execute(stmt)
    attempt = result.scalar_one_or_none()

    if not attempt:
        raise HTTPException(404, "Sessiya topilmadi")
    
    # 2. Agar imtihon allaqachon yakunlangan bo'lsa, natijani qaytarish
    if attempt.is_finished:
        return await get_mock_result_service(db, attempt_id)

    # 3. Topshirilgan ballarni yig'ish
    # is_checked bo'lganlarini olamiz, qolganlarini pastda 0.0 deb hisoblaymiz
    scores_map = {s.skill: s.scaled_score for s in attempt.skills if s.is_checked}
    
    # 🛑 MUHIM: 4 ta bo'lim shartini olib tashladik yoki yumshatdik
    # if len(scores_map) < 1:
    #     raise HTTPException(400, "Kamida bitta bo'lim topshirilgan bo'lishi kerak")

    # 4. Ballarni xavfsiz olish (Topshirilmagan bo'lsa 0.0)
    reading_ball = scores_map.get(SkillType.READING, 0.0)
    listening_ball = scores_map.get(SkillType.LISTENING, 0.0)
    writing_ball = scores_map.get(SkillType.WRITING, 0.0)
    speaking_ball = scores_map.get(SkillType.SPEAKING, 0.0)

    # 5. O'rtacha ballni hisoblash (IELTS standarti bo'yicha doim 4 ga bo'linadi)
    total_score = reading_ball + listening_ball + writing_ball + speaking_ball
    avg_score = total_score / 4

    # 6. Natija obyektini yaratish
    exam_result = MockExamResult(
        attempt_id=attempt.id,
        user_id=attempt.user_id,
        reading_ball=reading_ball,
        listening_ball=listening_ball,
        writing_ball=writing_ball,
        speaking_ball=speaking_ball,
        overall_score=round(avg_score, 1),
        cefr_level=get_cefr_level(avg_score)
    )

    # 7. Statusni yangilash
    attempt.is_finished = True
    attempt.finished_at = datetime.utcnow()
    
    try:
        db.add(exam_result)
        await db.commit()
        await db.refresh(exam_result)
        return exam_result
    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Natijani saqlashda xatolik: {str(e)}")

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
