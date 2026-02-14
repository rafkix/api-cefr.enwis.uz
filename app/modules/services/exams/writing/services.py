import logging
import json
import os
from typing import List, Any
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from openai import AsyncOpenAI 

from .models import WritingExam, WritingTask, WritingResult
from .schemas import WritingExamCreate, WritingExamUpdate, WritingSubmission

logger = logging.getLogger(__name__)

# OpenAI klientini sozlash
# Agar API Key bo'lmasa, xatolik bermasligi uchun try/except yoki shunchaki client yaratish
aclient = AsyncOpenAI(api_key="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")

class WritingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ================================================================
    #  AI EVALUATION (OpenAI)
    # ================================================================
    async def _evaluate_with_ai(self, task_type: str, topic: str, user_text: str) -> dict:
        """AI ga so'rov yuborish va baholash"""
        
        system_prompt = f"""
        You are a strict CEFR/IELTS Writing Examiner. Evaluate the student's writing based on Multilevel criteria.
        Task Type: {task_type}
        Topic: {topic}
        
        Evaluate these 5 criteria (0.0 - 10.0 scale):
        1. Task Achievement
        2. Coherence & Cohesion
        3. Vocabulary
        4. Grammar
        5. Punctuation & Spelling

        OUTPUT JSON FORMAT ONLY:
        {{
            "score": <float, average score>,
            "feedback": "<string, general feedback>",
            "criteria": {{
                "Task Achievement": <float>,
                "Coherence & Cohesion": <float>,
                "Vocabulary": <float>,
                "Grammar": <float>,
                "Punctuation & Spelling": <float>
            }},
            "suggestions": ["<suggestion 1>", "<suggestion 2>"]
        }}
        """

        try:
            # API Key yo'q bo'lsa yoki limit tugagan bo'lsa, xatolik chiqadi
            response = await aclient.chat.completions.create(
                model="gpt-3.5-turbo-1106", 
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text}
                ],
                temperature=0.3,
            )
            content = response.choices[0].message.content
            return json.loads(content)

        except Exception as e:
            logger.error(f"AI Error: {str(e)}")
            # Fallback (AI ishlamasa yoki puli tugagan bo'lsa)
            # Dastur to'xtab qolmasligi uchun 0 ball bilan qaytaradi
            return {
                "score": 0.0,
                "feedback": "AI evaluation temporarily unavailable (Check API Key or Quota).",
                "criteria": {
                    "Task Achievement": 0, "Coherence & Cohesion": 0,
                    "Vocabulary": 0, "Grammar": 0, "Punctuation & Spelling": 0
                },
                "suggestions": ["Please try again later."]
            }

    async def _create_tasks(self, exam_id: str, tasks_data: List[Any]):
        """Yordamchi: Tasklarni yaratish"""
        for t in tasks_data:
            new_task = WritingTask(
                exam_id=exam_id,
                part_number=t.part_number,
                type=t.type,
                topic=t.topic,
                instruction=t.instruction,
                context_text=t.context_text,
                min_words=t.min_words,
                max_words=t.max_words
            )
            self.db.add(new_task)

    # ================================================================
    #  CRUD METHODS
    # ================================================================

    async def create_exam(self, data: WritingExamCreate):
        try:
            new_exam = WritingExam(
                id=data.id,
                title=data.title,
                is_demo=data.isDemo,
                duration_minutes=data.duration_minutes
            )
            self.db.add(new_exam)
            await self.db.flush()
            
            if data.tasks:
                await self._create_tasks(new_exam.id, data.tasks)
            
            await self.db.commit()
            return await self.get_exam_by_id(new_exam.id)
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))

    async def get_all_exams(self):
        stmt = select(WritingExam).options(selectinload(WritingExam.tasks)).order_by(WritingExam.created_at.desc())
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_exam_by_id(self, exam_id: str):
        stmt = select(WritingExam).where(WritingExam.id == exam_id).options(selectinload(WritingExam.tasks))
        result = await self.db.execute(stmt)
        exam = result.unique().scalar_one_or_none()
        if not exam:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Exam not found")
        return exam

    async def update_exam(self, exam_id: str, data: WritingExamUpdate):
        exam = await self.get_exam_by_id(exam_id)
        try:
            update_data = data.dict(exclude_unset=True)
            if 'title' in update_data: exam.title = update_data['title']
            if 'isDemo' in update_data: exam.is_demo = update_data['isDemo']
            if 'duration_minutes' in update_data: exam.duration_minutes = update_data['duration_minutes']

            if data.tasks is not None:
                await self.db.execute(delete(WritingTask).where(WritingTask.exam_id == exam_id))
                await self.db.flush()
                await self._create_tasks(exam.id, data.tasks)

            await self.db.commit()
            return await self.get_exam_by_id(exam.id)
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))

    async def delete_exam(self, exam_id: str):
        stmt = select(WritingExam).where(WritingExam.id == exam_id)
        result = await self.db.execute(stmt)
        exam = result.scalar_one_or_none()
        if not exam:
            raise HTTPException(404, "Not found")
        
        await self.db.delete(exam)
        await self.db.commit()
        return {"success": True}

    # ================================================================
    #  SUBMIT & AI EVALUATION (TUZATILDI)
    # ================================================================

    async def submit_exam_with_ai(self, user_id: int, data: WritingSubmission):
        exam = await self.get_exam_by_id(data.exam_id)
        
        ai_results = {}
        total_score = 0
        
        # Har bir task uchun javoblarni tekshiramiz
        for task in exam.tasks:
            # Frontend task.id yoki part_number string sifatida yuborishi mumkin
            # Biz task.id (DB ID) ni stringga o'girib ishlatamiz
            task_id_str = str(task.id) 
            user_text = data.user_responses.get(task_id_str, "")
            
            if user_text:
                eval_result = await self._evaluate_with_ai(
                    task_type=task.type, topic=task.topic, user_text=user_text
                )
                ai_results[task_id_str] = eval_result
                total_score += eval_result.get('score', 0)
        
        new_result = WritingResult(
            user_id=user_id,
            exam_id=exam.id,
            user_responses=data.user_responses,
            overall_score=total_score,
            ai_evaluation=ai_results
        )
        
        try:
            self.db.add(new_result)
            await self.db.commit()
            await self.db.refresh(new_result)
            
            # --- MUHIM O'ZGARISH ---
            # Pydantic schemas.WritingResultDetailResponse strukturasiga moslash uchun
            # lug'at qaytaramiz.
            return {
                "summary": new_result, 
                "user_responses": data.user_responses
            }
            
        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=400, detail=f"Natijani saqlashda xatolik: {str(e)}")

    async def get_user_results(self, user_id: int):
        stmt = select(WritingResult).where(WritingResult.user_id == user_id).order_by(WritingResult.created_at.desc())
        res = await self.db.execute(stmt)
        return res.scalars().all()

    async def get_result_detail(self, result_id: int, user_id: int):
        stmt = select(WritingResult).where(WritingResult.id == result_id, WritingResult.user_id == user_id)
        res = await self.db.execute(stmt)
        result = res.scalar_one_or_none()
        
        if not result: return None
        
        # Bu yerda ham schema mosligi uchun dict qaytaramiz
        return {
            "summary": result, 
            "user_responses": result.user_responses
        }