import logging
from typing import List, Any, Tuple, Optional
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

# Mock Models (Integratsiya uchun)
from app.modules.services.exams.mock.models import (
    MockExamAttempt,
    MockExamResult,
    MockSkillAttempt,
    SkillType,
)

from .models import (
    ListeningExam, 
    ListeningPart, 
    ListeningQuestion, 
    ListeningQuestionOption, 
    ListeningPartOption,
    ListeningResult
)
from .schemas import ListeningExamCreate, ListeningExamUpdate, ListeningSubmission

logger = logging.getLogger(__name__)

class ListeningService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    #  SCORING LOGIC (BAHOLASH)
    # ================================================================
    def _calculate_metrics(self, correct_count: int) -> Tuple[float, str]:
        """
        Multilevel-bm.pdf hujjati asosida ball va darajani hisoblash.
        Manba:  jadvali.
        Maksimal ball: 75.
        """
        
        # 1. Daraja: B1 dan quyi
        # Manba: To'g'ri javoblar 0-9 -> Ball 0-37 
        if correct_count <= 9:
            # 0 dan 9 gacha bo'lgan oraliqni 0 dan 37 gacha bo'lgan ballga proporsional taqsimlash
            if correct_count == 0:
                return 0.0, "B1 dan quyi"
            std_score = (correct_count / 9) * 37
            return round(std_score, 1), "B1 dan quyi"
        
        # 2. Daraja: B1
        # Manba: To'g'ri javoblar 10-17 -> Ball 38-50 
        elif 10 <= correct_count <= 17:
            # Formula: MinBall + (Topgan - MinSavol) * ((MaxBall - MinBall) / (MaxSavol - MinSavol))
            # (50 - 38) / (17 - 10) = 12 / 7 ≈ 1.71 ball har bir savol uchun ushbu oraliqda
            std_score = 38 + (correct_count - 10) * ((50 - 38) / (17 - 10))
            return round(std_score, 1), "B1"
        
        # 3. Daraja: B2
        # Manba: To'g'ri javoblar 18-27 -> Ball 51-64 
        elif 18 <= correct_count <= 27:
            # (64 - 51) / (27 - 18) = 13 / 9 ≈ 1.44 ball har bir savol uchun ushbu oraliqda
            std_score = 51 + (correct_count - 18) * ((64 - 51) / (27 - 18))
            return round(std_score, 1), "B2"
            
        # 4. Daraja: C1
        # Manba: To'g'ri javoblar 28-35 -> Ball 65-75 
        # Eslatma: C2 darajasi ko'zda tutilmagan [cite: 23]
        elif correct_count >= 28:
            # Hisoblash uchun maksimal savollar sonini 35 deb olamiz (agar foydalanuvchi ko'proq topsa ham)
            capped_count = min(correct_count, 35)
            
            # (75 - 65) / (35 - 28) = 10 / 7 ≈ 1.42 ball har bir savol uchun ushbu oraliqda
            std_score = 65 + (capped_count - 28) * ((75 - 65) / (35 - 28))
            
            # Maksimal ball 75 dan oshmasligi kerak [cite: 24]
            return round(min(75.0, std_score), 1), "C1"
        
        return 0.0, "Aniqlanmagan"

    # ================================================================
    #  HELPERS (Yaratish uchun)
    # ================================================================
    async def _create_structure(self, exam_id: str, parts_data: List[Any]):
        for p_data in parts_data:
            new_part = ListeningPart(
                exam_id=exam_id,
                part_number=p_data.part_number,
                title=p_data.title,
                instruction=p_data.instruction,
                task_type=p_data.task_type,
                audio_url=p_data.audio_url, 
                context=p_data.context,
                passage=p_data.passage,
                map_image=p_data.map_image
            )
            self.db.add(new_part)
            await self.db.flush()

            if p_data.options:
                for opt in p_data.options:
                    self.db.add(ListeningPartOption(part_id=new_part.id, value=opt.value, label=opt.label))

            for q_data in p_data.questions:
                new_q = ListeningQuestion(
                    part_id=new_part.id,
                    question_number=q_data.question_number,
                    type=q_data.type,
                    text=q_data.text, 
                    correct_answer=q_data.correct_answer
                )
                self.db.add(new_q)
                await self.db.flush()

                if q_data.options:
                    for opt in q_data.options:
                        self.db.add(ListeningQuestionOption(question_id=new_q.id, value=opt.value, label=opt.label))

    # ================================================================
    #  CRUD METHODS
    # ================================================================
    async def create_exam(self, data: ListeningExamCreate):
        try:
            new_exam = ListeningExam(
                id=data.id,
                title=data.title,
                is_demo=data.is_demo,
                is_free=data.is_free,
                is_mock=data.is_mock,
                is_active=data.is_active,
                sections=data.sections,
                cefr_level=data.cefr_level,
                duration_minutes=data.duration_minutes,
                total_questions=data.total_questions
            )
            self.db.add(new_exam)
            await self.db.flush() 
            
            await self._create_structure(new_exam.id, data.parts)
            await self.db.commit()
            return await self.get_exam_by_id(new_exam.id)
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(400, detail=f"Xatolik: {str(e)}")

    async def get_all_exams(self):
        stmt = select(ListeningExam).order_by(ListeningExam.created_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_exam_by_id(self, exam_id: str):
        stmt = select(ListeningExam).where(ListeningExam.id == exam_id).options(
            selectinload(ListeningExam.parts).options(
                selectinload(ListeningPart.questions).selectinload(ListeningQuestion.options),
                selectinload(ListeningPart.options)
            )
        )
        res = await self.db.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def update_exam(self, exam_id: str, data: ListeningExamUpdate):
        exam = await self.db.get(ListeningExam, exam_id)
        if not exam:
            raise HTTPException(404, detail="Imtihon topilmadi")

        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key != "parts":
                setattr(exam, key, value)

        if data.parts:
            await self.db.execute(delete(ListeningPart).where(ListeningPart.exam_id == exam_id))
            await self.db.flush()
            await self._create_structure(exam.id, data.parts)

        await self.db.commit()
        return await self.get_exam_by_id(exam_id)

    async def delete_exam(self, exam_id: str):
        exam = await self.db.get(ListeningExam, exam_id)
        if not exam:
            return False
        await self.db.delete(exam)
        await self.db.commit()
        return True

    # ================================================================
    #  RESULTS & SUBMISSION
    # ================================================================
    async def submit_exam_and_get_result(self, user_id: int, data: ListeningSubmission):
        exam = await self.get_exam_by_id(data.exam_id)
        if not exam:
            raise HTTPException(404, detail="Imtihon topilmadi")
        
        correct_count, total_q, review_items = 0, 0, []
        
        for part in exam.parts:
            for q in part.questions:
                total_q += 1
                user_ans = data.user_answers.get(str(q.id), "").strip().lower()
                correct_ans_list = [a.strip().lower() for a in q.correct_answer.split("/")]
                
                is_correct = user_ans in correct_ans_list
                if is_correct: 
                    correct_count += 1
                
                review_items.append({
                    "question_number": q.question_number,
                    "user_answer": data.user_answers.get(str(q.id), ""),
                    "correct_answer": q.correct_answer,
                    "is_correct": is_correct,
                    "type": q.type
                })

        std_score, cefr_level = self._calculate_metrics(correct_count)
        
        new_result = ListeningResult(
            user_id=user_id,
            exam_id=exam.id,
            exam_attempt_id=data.exam_attempt_id,
            raw_score=correct_count,
            standard_score=std_score,
            cefr_level=cefr_level,
            percentage=round((correct_count / total_q) * 100, 2) if total_q > 0 else 0,
            user_answers=data.user_answers
        )
        
        self.db.add(new_result)
        await self.db.flush() # ID olish uchun flush

        # MOCK INTEGRATION: Agar bu Mock bo'lsa, statusni yangilaymiz
        if data.exam_attempt_id:
            await self._update_mock_listening(data.exam_attempt_id, std_score, cefr_level)

        await self.db.commit()
        await self.db.refresh(new_result)
        
        return {"summary": new_result, "review": review_items}

    async def get_user_results(self, user_id: int):
        stmt = (
            select(ListeningResult)
            .where(ListeningResult.user_id == user_id)
            .order_by(ListeningResult.created_at.desc())
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()
    
    async def get_result_with_review(self, result_id: int, user_id: int):
        stmt = select(ListeningResult).where(
            ListeningResult.id == result_id, 
            ListeningResult.user_id == user_id
        )
        res = await self.db.execute(stmt)
        result_data = res.scalar_one_or_none()
        
        if not result_data:
            return None 

        exam = await self.get_exam_by_id(result_data.exam_id)
        if not exam:
            return None
        
        review_data = []
        for part in exam.parts:
            for q in part.questions:
                u_ans = result_data.user_answers.get(str(q.id), "").strip().lower()
                c_ans_raw = q.correct_answer.strip().lower()
                valid_options = [a.strip() for a in c_ans_raw.split("/")]
                
                is_correct = u_ans in valid_options
                
                review_data.append({
                    "question_number": q.question_number,
                    "user_answer": result_data.user_answers.get(str(q.id), ""),
                    "correct_answer": q.correct_answer,
                    "is_correct": is_correct,
                    "type": q.type
                })
                
        return {
            "summary": result_data,
            "review": review_data
        }

    # ================================================================
    #  MOCK EXAM INTEGRATION (INTERNAL)
    # ================================================================
    async def _update_mock_listening(self, exam_attempt_id: int, score: float, cefr_level: str):
        """Mock imtihonning Listening qismini yangilash"""
        stmt = select(MockSkillAttempt).where(
            MockSkillAttempt.attempt_id == exam_attempt_id,
            MockSkillAttempt.skill == SkillType.LISTENING,
        )
        skill = (await self.db.execute(stmt)).scalar_one_or_none()
        if skill:
            skill.score = score
            skill.cefr_level = cefr_level
            skill.is_checked = True
            skill.submitted_at = datetime.now(timezone.utc)
            await self.db.flush()
            # Barcha skillar tugaganini tekshirish
            await self._try_finish_mock_exam(exam_attempt_id)

    async def _try_finish_mock_exam(self, exam_attempt_id: int):
        """Barcha 4 skill topshirilgan bo'lsa Mockni yakunlash"""
        stmt = select(MockSkillAttempt).where(MockSkillAttempt.attempt_id == exam_attempt_id)
        skills = (await self.db.execute(stmt)).scalars().all()

        # Agar 4 ta skill ham tekshirib bo'lingan bo'lsa
        if len(skills) == 4 and all(s.is_checked for s in skills):
            r = next(s for s in skills if s.skill == SkillType.READING)
            l = next(s for s in skills if s.skill == SkillType.LISTENING)
            w = next(s for s in skills if s.skill == SkillType.WRITING)
            sp = next(s for s in skills if s.skill == SkillType.SPEAKING)

            overall = round((r.score + l.score + w.score + sp.score) / 4, 2)
            
            # O'rtacha ballni CEFR ga o'tkazish (Taxminiy hisob)
            # Source 35: B1 (38-50), B2 (51-64), C1 (65-75)
            final_cefr = "B1 dan quyi"
            if overall >= 65:
                final_cefr = "C1"
            elif overall >= 51:
                final_cefr = "B2"
            elif overall >= 38:
                final_cefr = "B1"

            self.db.add(MockExamResult(
                attempt_id=exam_attempt_id,
                reading_score=r.score,
                listening_score=l.score,
                writing_score=w.score,
                speaking_score=sp.score,
                overall_score=overall,
                cefr_level=final_cefr,
                passed=overall >= 38, # B1 dan yuqori bo'lsa o'tgan hisoblanadi 
            ))

            attempt = await self.db.get(MockExamAttempt, exam_attempt_id)
            if attempt:
                attempt.is_finished = True
                attempt.finished_at = datetime.now(timezone.utc)