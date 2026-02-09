import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple, Any

from fastapi import HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Mock Models (Integratsiya uchun)
from app.modules.services.exams.mock.models import (
    MockExamAttempt,
    MockExamResult,
    MockSkillAttempt,
    SkillType,
)

# Reading Models & Schemas
from .models import (
    ReadingTest,
    ReadingPart,
    ReadingQuestion,
    ReadingOption,
    ReadingResult,
)
from .schemas import (
    ReadingTestCreate,
    ReadingTestUpdate,
    ReadingSubmitRequest,
    ReadingResultResponse,
    ReadingResultDetailResponse,
    ReadingQuestionReview,
)

logger = logging.getLogger(__name__)

class ReadingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    #  1. BAHOLASH MANTIQI (Multilevel-bm.pdf, 35-jadval asosida)
    # ================================================================
    def _calculate_metrics(self, correct_count: int) -> Tuple[float, str]:
        """
        Multilevel mezonlari bo'yicha ballni hisoblash.
        Maksimal ball: 75[cite: 24].
        """
        
        # 1. B1 dan quyi (0-9 ta javob -> 0-37 ball) 
        if correct_count <= 9:
            if correct_count == 0: return 0.0, "B1 dan quyi"
            std_score = (correct_count / 9) * 37
            return round(std_score, 1), "B1 dan quyi"

        # 2. B1 daraja (10-17 ta javob -> 38-50 ball) 
        elif 10 <= correct_count <= 17:
            # Interpolatsiya: 38 + (count-10) * ((50-38)/(17-10))
            std_score = 38 + (correct_count - 10) * (12 / 7)
            return round(std_score, 1), "B1"
        
        # 3. B2 daraja (18-27 ta javob -> 51-64 ball) 
        elif 18 <= correct_count <= 27:
            # Interpolatsiya: 51 + (count-18) * ((64-51)/(27-18))
            std_score = 51 + (correct_count - 18) * (13 / 9)
            return round(std_score, 1), "B2"
            
        # 4. C1 daraja (28-35 ta javob -> 65-75 ball) 
        elif correct_count >= 28:
            capped_count = min(correct_count, 35)
            # Interpolatsiya: 65 + (count-28) * ((75-65)/(35-28))
            std_score = 65 + (capped_count - 28) * (10 / 7)
            return round(min(75.0, std_score), 1), "C1"
        
        return 0.0, "Aniqlanmagan"

    # ================================================================
    #  2. TESTLARNI BOSHQARISH (CRUD)
    # ================================================================
    async def create_test(self, data: ReadingTestCreate) -> ReadingTest:
        test = ReadingTest(
            id=data.id, title=data.title, cefr_level=data.cefr_level,
            language=data.language, duration_minutes=data.duration_minutes,
            total_questions=data.total_questions, is_demo=data.is_demo,
            is_free=data.is_free, is_mock=data.is_mock, is_active=data.is_active,
        )

        for part_data in data.parts:
            part = ReadingPart(
                title=part_data.title, description=part_data.description,
                passage=part_data.passage,
            )
            for q in part_data.questions:
                question = ReadingQuestion(
                    question_number=q.question_number, type=q.type,
                    text=q.text, correct_answer=q.correct_answer,
                    word_limit=q.word_limit,
                )
                for opt in q.options or []:
                    question.options.append(ReadingOption(label=opt.label, value=opt.value))
                part.questions.append(question)
            test.parts.append(part)

        self.db.add(test)
        await self.db.commit()
        return await self.get_test_by_id(test.id)

    async def get_all_tests(self) -> List[ReadingTest]:
        # 'selectinload' ishlatilishi shart (MissingGreenlet xatosi uchun)
        stmt = (
            select(ReadingTest)
            .options(
                selectinload(ReadingTest.parts)
                .selectinload(ReadingPart.questions)
                .selectinload(ReadingQuestion.options)
            )
            .order_by(ReadingTest.created_at.desc())
        )
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def get_test_by_id(self, test_id: str) -> Optional[ReadingTest]:
        stmt = (
            select(ReadingTest).where(ReadingTest.id == test_id)
            .options(
                selectinload(ReadingTest.parts)
                .selectinload(ReadingPart.questions)
                .selectinload(ReadingQuestion.options)
            )
        )
        res = await self.db.execute(stmt)
        return res.unique().scalar_one_or_none()

    async def update_test(self, test_id: str, data: ReadingTestUpdate) -> ReadingTest:
        test = await self.get_test_by_id(test_id)
        if not test: raise HTTPException(404, "Reading test topilmadi")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field != "parts": setattr(test, field, value)

        if data.parts is not None:
            await self.db.execute(delete(ReadingPart).where(ReadingPart.test_id == test_id))
            for part_data in data.parts:
                part = ReadingPart(
                    test_id=test_id, title=part_data.title,
                    description=part_data.description, passage=part_data.passage,
                )
                for q in part_data.questions:
                    question = ReadingQuestion(
                        question_number=q.question_number, type=q.type,
                        text=q.text, correct_answer=q.correct_answer,
                        word_limit=q.word_limit,
                    )
                    for opt in q.options or []:
                        question.options.append(ReadingOption(label=opt.label, value=opt.value))
                    part.questions.append(question)
                self.db.add(part)

        await self.db.commit()
        return await self.get_test_by_id(test_id)

    async def delete_test(self, test_id: str) -> bool:
        test = await self.db.get(ReadingTest, test_id)
        if not test: return False
        await self.db.delete(test)
        await self.db.commit()
        return True

    # ================================================================
    #  3. JAVOBLARNI TEKSHIRISH (SUBMIT)
    # ================================================================
    async def submit_answers(self, user_id: int, test_id: str, data: ReadingSubmitRequest) -> ReadingResultDetailResponse:
        test = await self.get_test_by_id(test_id)
        if not test: raise HTTPException(404, "Test topilmadi")

        correct_count, total_count = 0, 0
        review_items: List[ReadingQuestionReview] = []
        user_answers_map = {str(a.question_id): a.answers for a in data.answers}

        for part in test.parts:
            for q in part.questions:
                total_count += 1
                u_ans = user_answers_map.get(str(q.id), [])
                c_ans = q.correct_answer
                
                # FIX: Javob List yoki String bo'lsa ham ishlaydi
                if isinstance(c_ans, list):
                    c_clean_options = [str(opt).strip().lower() for opt in c_ans]
                else:
                    c_clean_options = [str(opt).strip().lower() for opt in str(c_ans).split('/')]
                
                u_val = str(u_ans[0]).strip().lower() if u_ans else ""
                
                is_correct = u_val in c_clean_options
                if is_correct: correct_count += 1

                review_items.append(ReadingQuestionReview(
                    question_number=q.question_number, user_answer=u_ans,
                    correct_answer=c_ans, is_correct=is_correct, type=q.type,
                ))

        # Ballni hisoblash
        std_score, cefr = self._calculate_metrics(correct_count)
        percentage = round((correct_count / total_count) * 100, 2) if total_count > 0 else 0.0

        result = ReadingResult(
            user_id=user_id,
            test_id=test_id,
            exam_attempt_id=data.exam_attempt_id,
            raw_score=correct_count,
            percentage=percentage,
            standard_score=std_score,  # ⚠️ BAZADA USTUN BO'LISHI SHART!
            cefr_level=cefr,
            user_answers=user_answers_map,
        )

        self.db.add(result)
        await self.db.flush()

        # Mock imtihon bo'lsa yangilash
        if data.exam_attempt_id:
            await self._update_mock_reading(data.exam_attempt_id, std_score, cefr)

        await self.db.commit()
        
        # FIX: Pydantic V2 (model_validate)
        return ReadingResultDetailResponse(
            summary=ReadingResultResponse.model_validate(result),
            review=review_items,
        )

    async def get_user_results(self, user_id: int) -> List[ReadingResult]:
        stmt = select(ReadingResult).where(ReadingResult.user_id == user_id).order_by(ReadingResult.created_at.desc())
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def get_result_with_review(self, result_id: int, user_id: int) -> Optional[ReadingResultDetailResponse]:
        stmt = select(ReadingResult).where(ReadingResult.id == result_id, ReadingResult.user_id == user_id)
        res = await self.db.execute(stmt)
        result = res.scalar_one_or_none()
        
        if not result: return None

        test = await self.get_test_by_id(result.test_id)
        if not test: return None

        review_items = []
        for part in test.parts:
            for q in part.questions:
                u_ans = result.user_answers.get(str(q.id), [])
                c_ans = q.correct_answer
                
                # Review qismida ham FIX
                if isinstance(c_ans, list):
                    c_clean_options = [str(opt).strip().lower() for opt in c_ans]
                else:
                    c_clean_options = [str(opt).strip().lower() for opt in str(c_ans).split('/')]
                
                u_val = str(u_ans[0]).strip().lower() if u_ans else ""
                is_correct = u_val in c_clean_options

                review_items.append(ReadingQuestionReview(
                    question_number=q.question_number, user_answer=u_ans,
                    correct_answer=c_ans, is_correct=is_correct, type=q.type,
                ))

        return ReadingResultDetailResponse(
            summary=ReadingResultResponse.model_validate(result),
            review=review_items
        )

    # ================================================================
    #  4. MOCK EXAM INTEGRATION
    # ================================================================
    async def _update_mock_reading(self, exam_attempt_id: int, score: float, cefr_level: str):
        stmt = select(MockSkillAttempt).where(
            MockSkillAttempt.attempt_id == exam_attempt_id,
            MockSkillAttempt.skill == SkillType.READING,
        )
        skill = (await self.db.execute(stmt)).scalar_one_or_none()
        if skill:
            skill.score = score
            skill.cefr_level = cefr_level
            skill.is_checked = True
            skill.submitted_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self._try_finish_mock_exam(exam_attempt_id)

    async def _try_finish_mock_exam(self, exam_attempt_id: int):
        stmt = select(MockSkillAttempt).where(MockSkillAttempt.attempt_id == exam_attempt_id)
        skills = (await self.db.execute(stmt)).scalars().all()

        if len(skills) == 4 and all(s.is_checked for s in skills):
            r = next(s for s in skills if s.skill == SkillType.READING)
            l = next(s for s in skills if s.skill == SkillType.LISTENING)
            w = next(s for s in skills if s.skill == SkillType.WRITING)
            sp = next(s for s in skills if s.skill == SkillType.SPEAKING)

            overall = round((r.score + l.score + w.score + sp.score) / 4, 2)
            
            # Yakuniy CEFR 
            final_cefr = "B1 dan quyi"
            if overall >= 65: final_cefr = "C1"
            elif overall >= 51: final_cefr = "B2"
            elif overall >= 38: final_cefr = "B1"

            self.db.add(MockExamResult(
                attempt_id=exam_attempt_id,
                reading_score=r.score, listening_score=l.score,
                writing_score=w.score, speaking_score=sp.score,
                overall_score=overall, cefr_level=final_cefr,
                passed=overall >= 38, # B1 (38 ball) dan o'tgan hisoblanadi
            ))

            attempt = await self.db.get(MockExamAttempt, exam_attempt_id)
            if attempt:
                attempt.is_finished = True
                attempt.finished_at = datetime.now(timezone.utc)