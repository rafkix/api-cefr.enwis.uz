import logging
import json
from typing import List, Dict, Any, Optional
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

# Loyihangizdagi ichki modullar
from app.modules.services.exams.mock.models import MockExamResult
from groq import AsyncGroq

# Modellaringiz va Sxemalaringiz
from .models import WritingExam, WritingTask, WritingResult, WritingTaskType
from .schemas import (
    WritingExamCreate, WritingExamUpdate, 
    WritingSubmission, WritingResultResponse
)

import io
import html
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, 
    TableStyle, PageBreak, HRFlowable
)
from reportlab.lib.units import mm

logger = logging.getLogger(__name__)

# Groq AI Klienti (Barqaror ishlashi uchun core/config dan olish tavsiya etiladi)
# Llama 3.3 modeli CEFR mezonlarini juda yaxshi tushunadi
groq_client = AsyncGroq(api_key="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")

class WritingService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.groq_client = groq_client

    # ================================================================
    # 1. EXAM MANAGEMENT (Admin uchun CRUD) - O'zgarishsiz qoldi
    # ================================================================

    async def create_exam(self, data: WritingExamCreate) -> WritingExam:
        try:
            new_exam = WritingExam(
                id=data.id,
                title=data.title,
                cefr_level=data.cefr_level,
                duration_minutes=data.duration_minutes,
                is_demo=data.is_demo,
                is_free=data.is_free,
                is_mock=data.is_mock,
                is_active=data.is_active
            )
            self.db.add(new_exam)
            await self.db.flush() 
            
            for t in data.tasks:
                new_task = WritingTask(
                    exam_id=new_exam.id,
                    part_number=t.part_number,
                    type=t.type,
                    topic=t.topic,
                    instruction=t.instruction,
                    context_text=t.context_text,
                    min_words=t.min_words,
                    max_words=t.max_words
                )
                self.db.add(new_task)
            
            await self.db.commit()
            return await self.get_exam_by_id(new_exam.id)
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Exam creation error: {e}")
            raise HTTPException(400, detail=f"Imtihon yaratishda xatolik: {str(e)}")

    async def get_exam_by_id(self, exam_id: str) -> WritingExam:
        stmt = select(WritingExam).where(WritingExam.id == exam_id).options(selectinload(WritingExam.tasks))
        res = await self.db.execute(stmt)
        exam = res.unique().scalar_one_or_none()
        if not exam:
            raise HTTPException(404, "Imtihon topilmadi")
        return exam

    async def get_all_exams(self, active_only: bool = False) -> List[WritingExam]:
        stmt = select(WritingExam).options(selectinload(WritingExam.tasks))
        if active_only:
            stmt = stmt.where(WritingExam.is_active == True)
        res = await self.db.execute(stmt)
        return list(res.scalars().unique().all())
    
    async def update_exam(self, exam_id: str, data: WritingExamUpdate) -> WritingExam:
        """Imtihon ma'lumotlarini va savollarini tahrirlash"""
        exam = await self.get_exam_by_id(exam_id)
        
        # Asosiy maydonlarni yangilash
        obj_data = data.model_dump(exclude={'tasks'}, exclude_unset=True)
        for key, value in obj_data.items():
            setattr(exam, key, value)
        
        # Agar tasks berilgan bo'lsa, eskilarini o'chirib yangilarini qo'shish
        if data.tasks is not None:
            await self.db.execute(delete(WritingTask).where(WritingTask.exam_id == exam_id))
            for t in data.tasks:
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
        
        try:
            await self.db.commit()
            await self.db.refresh(exam)
            return exam
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Update exam error: {e}")
            raise HTTPException(400, detail="Yangilashda xatolik yuz berdi")

    async def delete_exam(self, exam_id: str):
        exam = await self.get_exam_by_id(exam_id)
        await self.db.delete(exam)
        await self.db.commit()
        return {"status": "success", "message": f"Exam {exam_id} deleted"}
    
    # ================================================================
    # 2. RESULT RETRIEVAL (Siz so'ragan metodlar)
    # ================================================================

    async def get_all_results(self) -> List[WritingResult]:
        """Barcha foydalanuvchilarning natijalari (Admin panel uchun)"""
        stmt = select(WritingResult).order_by(WritingResult.created_at.desc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_user_results(self, user_id: int) -> List[WritingResult]:
        """Foydalanuvchining shaxsiy imtihon tarixini olish"""
        stmt = select(WritingResult).where(WritingResult.user_id == user_id).order_by(WritingResult.created_at.desc())
        res = await self.db.execute(stmt)
        return list(res.scalars().all())

    async def get_result_by_id(self, result_id: int) -> WritingResult:
        """Aniq bitta natijani (Exam/Topic ma'lumotlari bilan) yuklash"""
        # options(joinedload(...)) orqali exam jadvalini birga olib kelamiz
        stmt = (
            select(WritingResult)
            .options(joinedload(WritingResult.exam)) 
            .where(WritingResult.id == result_id)
        )
        res = await self.db.execute(stmt)
        result = res.scalar_one_or_none()
        
        if not result:
            raise HTTPException(404, "Natija topilmadi")
        return result

    # ================================================================
    # 3. SUBMISSION & BAA 2025 OFFICIAL SCORING logic
    # ================================================================
    async def submit_exam_with_ai(self, user_id: int, data: WritingSubmission):
        # 1. Imtihon ma'lumotlarini olish
        exam = await self.get_exam_by_id(data.exam_id)
        ai_evals = {}
        part1_scores = []  # Task 1.1 va 1.2 uchun
        part2_score = 0.0  # Task 2 uchun
        
        # 2. Har bir topshiriqni tahlil qilish
        for task in exam.tasks:
            # Task turiga qarab kalitlarni aniqlash
            if task.type == WritingTaskType.TASK_1_1_INFORMAL:
                task_key = "task1.1"
                resp_id = "1"
            elif task.type == WritingTaskType.TASK_1_2_FORMAL:
                task_key = "task1.2"
                resp_id = "2"
            else: # TASK_2_ESSAY
                task_key = "task2"
                resp_id = "3"

            user_text = (data.user_responses.get(resp_id) or "").strip()
            word_count = len(user_text.split())

            # Boshlang'ich natija strukturasi
            evaluation_result = {
                "task_title": task.type,
                "score": 0.0,
                "wordCount": word_count,
                "penalty": 0.0,
                "feedback": "Tahlil uchun matn yetarli emas.",
                "criteria": {
                    "taskAchievement": 0, 
                    "grammar": 0, 
                    "vocabulary": 0, 
                    "coherence": 0, 
                    "mechanics": 0
                },
                "suggestions": []
            }

            # Hajm tekshiruvi (BAA 2025 qoidalari bo'yicha)
            min_limit = 0.6 if task_key != "task2" else 1.3
            is_valid = word_count > 10 # Juda qisqa matnlarni AI ga yubormaymiz

            if is_valid:
                try:
                    # AI TAHLIL
                    eval_data = await self._evaluate_with_ai(
                        task_type=task.type, 
                        topic=task.topic, 
                        user_text=user_text,
                        part_number=task_key
                    )
                    
                    if eval_data:
                        penalty = self._calculate_length_penalty(task_key, word_count)
                        ai_score = float(eval_data.get('score', 0.0))
                        
                        # Jarima bilan hisoblangan yakuniy ball
                        current_task_score = max(min_limit, ai_score - penalty)
                        
                        evaluation_result.update(eval_data)
                        evaluation_result["score"] = current_task_score
                        evaluation_result["penalty"] = penalty
                except Exception as e:
                    print(f"AI Error for {task_key}: {e}")
                    evaluation_result["score"] = min_limit

            # Lug'atga saqlash (Overwrite bo'lmasligi kafolatlanadi)
            ai_evals[task_key] = evaluation_result

            # Umumiy ball uchun yig'ish
            if task_key.startswith("task1"):
                part1_scores.append(evaluation_result["score"])
            else:
                part2_score = evaluation_result["score"]

        # 3. RASMIY FORMULA (Part 1: 33%, Part 2: 67%)
        try:
            # Part 1 o'rtachasi (1.1 va 1.2 bo'lsa ikkalasining o'rtachasi)
            avg_p1 = sum(part1_scores) / len(part1_scores) if part1_scores else 0.0
            
            # Vaznli ball (weighted score)
            weighted_avg = (avg_p1 * 0.33) + (part2_score * 0.67)
            
            # Multilevel 0-36 shkalasiga o'tkazish
            raw_expert_score = round(weighted_avg * 4, 1) 
            final_scaled_score = self._convert_to_75_scale(raw_expert_score)
        except Exception as e:
            print(f"Calculation Error: {e}")
            raw_expert_score = 0.0
            final_scaled_score = 0

        # 4. DBga SAQLASH
        result_record = WritingResult(
            user_id=user_id,
            exam_id=exam.id,
            exam_attempt_id=data.attempt_id,
            user_responses=data.user_responses,
            raw_score=raw_expert_score,
            overall_score=final_scaled_score,
            ai_evaluation=ai_evals # Endi bu yerda 3 ta task bo'ladi
        )
        
        self.db.add(result_record)
        await self.db.commit()
        await self.db.refresh(result_record)

        return result_record

    # ================================================================
    # 3. JARIMA VA KONVERSIYA LOGIKASI
    # ================================================================
    def _calculate_length_penalty(self, task_key: str, count: int) -> float:
        """Hujjatdagi B2 daraja uchun jarima ballari"""
        if task_key == "task1.2":
            if 120 <= count <= 135: return 1.0
            if 105 <= count <= 119: return 2.0
            if 90 <= count <= 104: return 3.0
            if 75 <= count <= 89: return 4.0
        elif task_key == "task2":
            if 205 <= count <= 230: return 1.0
            if 180 <= count <= 204: return 2.0
            if 150 <= count <= 179: return 3.0
            if 125 <= count <= 149: return 4.0
        return 0.0

    def _convert_to_75_scale(self, score: float) -> int:
        """BAA 2025 rasmiy konversiya jadvali"""
        if score >= 35.1: return 75
        if score >= 30.1: return 67
        if score >= 28.1: return 65  # C1 darajasi boshlanishi
        if score >= 20.1: return 50  # B2 darajasi boshlanishi
        if score >= 14.1: return 38  # B1 darajasi boshlanishi
        if score >= 10.1: return 30
        if score >= 1.1:  return 12
        return 0

    # ================================================================
    # 4. AI ENGINE
    # ================================================================
    async def _evaluate_with_ai(self, task_type: str, topic: str, user_text: str, part_number: str) -> dict:
        # Hujjatdagi (source: 13-16, 42) jarima va hajm talablari
        config = {
            "task1.1": {"type": "Informal Letter", "min_words": 75, "max_words": 150, "penalty_threshold": 135},
            "task1.2": {"type": "Formal Letter", "min_words": 75, "max_words": 150, "penalty_threshold": 135},
            "task2": {"type": "Academic Essay", "min_words": 125, "max_words": 250, "penalty_threshold": 230}
        }.get(part_number)

        word_count = len(user_text.split())

        system_prompt = f"""
        You are an official Writing Examiner for the Agency for Knowledge Assessment (BAA) Multilevel system.
        Evaluate the student's response based on the official B2/C1 Assessment Criteria[cite: 1, 60].

        TASK SETTINGS:
        - Part: {part_number} ({config['type']})
        - Topic: {topic}
        - Word Count: {word_count}
        - Minimum Required: {config['min_words']} words. (If less than half, score is 0.6 for Task 1 or 1.3 for Task 2) .

        SCORING RUBRIC (4-point scale per criterion as per document):
        1. Task Achievement (Task requirements, Purpose, Register)[cite: 8, 40, 41]:
        - 4 pts: Full adherence to register (formal/academic), clear purpose, all bullet points covered.
        - 1 pt: Informal register in formal tasks, purpose not stated, bullet points missing.
        2. Coherence and Cohesion (Logic, Paragraphing, Linking devices):
        - 4 pts: Logical sequence, correct paragraphing, variety of complex cohesive devices.
        - 1 pt: No logic, no paragraphs, no cohesive devices.
        3. Lexical Resource (Vocabulary range, Precision, Paraphrase)[cite: 9, 37, 41]:
        - 4 pts: Wide range, complex words used correctly, effective paraphrasing.
        4. Grammatical Range and Accuracy (Sentence variety, Punctuation)[cite: 8, 39]:
        - 3-4 pts: Mix of simple and complex sentences, no errors or minor errors that don't impede meaning.

        WORD COUNT PENALTY RULES (Apply to final calculation):
        - For Task 1: 135-120 words (-1 pt), 119-105 (-2 pts), 104-90 (-3 pts), 89-75 (-4 pts)[cite: 13, 14, 15, 16].
        - For Task 2: 230-205 words (-1 pt), 204-180 (-2 pts), 179-150 (-3 pts), 149-125 (-4 pts)[cite: 42].

        OUTPUT FORMAT:
        Return ONLY a JSON object. All feedback must be professional, supportive, and in English.
        
        REQUIRED JSON STRUCTURE:
        {{
            "score": 0.0, (Calculated out of 9.0 after conversion)
            "rawScore": 0, (Total points from criteria 1-16)
            "penalty": 0, (Points deducted for word count)
            "feedback": "...",
            "criteria": {{
                "taskAchievement": 0.0,
                "coherence": 0.0,
                "vocabulary": 0.0,
                "grammar": 0.0,
                "mechanics": 0.0
            }},
            "suggestions": ["suggestion 1", "suggestion 2", "suggestion 3"]
        }}
        """

        try:
            response = await self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Student Text: {user_text}, Question: {topic}, Task Type: {task_type}"}
                ],
                model="llama-3.3-70b-versatile",
                response_format={"type": "json_object"},
                temperature=0.2 # Biroq ko'proq kreativlik va batafsil tahlil uchun biroz oshirdik
            )
            
            eval_data = json.loads(response.choices[0].message.content)
            
            # Kelayotgan ma'lumot list bo'lishini qat'iy tekshiramiz (FastAPI xato bermasligi uchun)
            if isinstance(eval_data.get("suggestions"), str):
                eval_data["suggestions"] = [eval_data["suggestions"]]
                
            return eval_data
            
        except Exception as e:
            print(f"Groq API Error: {e}")
            return None
        
    async def generate_pdf_report(self, result) -> io.BytesIO:
        """Natijani PDF shaklida professional dizaynda yaratish (Tuzatilgan versiya)"""
        try:
            buffer = io.BytesIO()
            
            # Metadata tayyorlash
            exam_title = result.exam.title if result.exam else "Writing Exam"
            overall_band = str(result.overall_score) if result.overall_score else "0"
            raw_score = str(result.raw_score) if result.raw_score else "0"
            date_str = result.created_at.strftime("%Y-%m-%d %H:%M") if isinstance(result.created_at, datetime) else "N/A"
            
            doc = SimpleDocTemplate(
                buffer, 
                pagesize=A4,
                title=f"Writing_Report_{result.id}",
                rightMargin=15*mm, leftMargin=15*mm,
                topMargin=15*mm, bottomMargin=15*mm
            )
            
            styles = getSampleStyleSheet()
            
            # --- MAXSUS STILLAR ---
            title_style = ParagraphStyle('Title', parent=styles['Heading1'], alignment=1, fontSize=22, textColor=colors.HexColor("#0f172a"), spaceAfter=12)
            brand_style = ParagraphStyle('Brand', parent=styles['Normal'], alignment=1, fontSize=12, textColor=colors.HexColor("#f97316"), fontName='Helvetica-Bold')
            section_style = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=16, textColor=colors.HexColor("#1e40af"), spaceBefore=15, spaceAfter=10)
            
            text_style = ParagraphStyle('Text', parent=styles['Normal'], fontSize=10, leading=14, alignment=4, spaceBefore=5, spaceAfter=5) 
            label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=5)
            
            block_style = ParagraphStyle(
                'Block', parent=styles['Normal'], fontSize=10, leading=14, 
                leftIndent=5*mm, rightIndent=5*mm,
                textColor=colors.HexColor("#334155"), backColor=colors.HexColor("#f1f5f9"),
                borderPadding=10, alignment=4, spaceBefore=5, spaceAfter=5
            )

            elements = []

            # 1. HEADER
            elements.append(Paragraph("ENWIS.UZ", brand_style))
            elements.append(Paragraph("OFFICIAL WRITING REPORT", title_style))
            elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0f172a"), spaceAfter=5))
            elements.append(Spacer(1, 8*mm))
            
            # 2. XULOSA JADVALI
            summary_data = [
                [Paragraph("<b>Exam:</b>", text_style), exam_title, Paragraph("<b>Overall Score:</b>", text_style), f"{overall_band} / 75"],
                [Paragraph("<b>Date:</b>", text_style), date_str, Paragraph("<b>Raw Score:</b>", text_style), f"{raw_score} / 36"]
            ]
            st = Table(summary_data, colWidths=[20*mm, 70*mm, 40*mm, 40*mm])
            st.setStyle(TableStyle([
                ('BACKGROUND', (2, 0), (3, 1), colors.HexColor("#eff6ff")),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('PADDING', (0, 0), (-1, -1), 6),
            ]))
            elements.append(st)
            elements.append(Spacer(1, 12*mm))

            # 3. TASKS LOOP
            evals = result.ai_evaluation or {}
            sorted_keys = sorted(evals.keys())

            for index, task_key in enumerate(sorted_keys):
                if index > 0:
                    elements.append(PageBreak())

                task_data = evals[task_key]
                task_name = task_key.replace("task", "TASK ").upper()
                
                elements.append(Paragraph(f"{task_name} ANALYSIS", section_style))
                elements.append(HRFlowable(width="40%", thickness=2, color=colors.HexColor("#1e40af"), hAlign='LEFT', spaceAfter=10))
                
                # --- TOPIK VA SAVOL MATNINI BIRLASHTIRIB OLISH ---
                # --- TOPIK VA SAVOL MATNINI BIRLASHTIRIB OLISH ---
                full_question_content = "Question content not available."
                if result.exam and result.exam.tasks:
                    target_type = {
                        "task1.1": WritingTaskType.TASK_1_1_INFORMAL,
                        "task1.2": WritingTaskType.TASK_1_2_FORMAL,
                        "task2": WritingTaskType.TASK_2_ESSAY
                    }.get(task_key)
                    
                    for t_obj in result.exam.tasks:
                        if t_obj.type == target_type:
                            # Yo'riqnoma, Mavzu, Kontekst va So'zlar sonini birlashtirish
                            parts = []
                            if t_obj.instruction: 
                                parts.append(f"<b>Instructions:</b><br/>{t_obj.instruction}")
                            if t_obj.topic: 
                                # Mavzu, ContextText va so'z chegaralarini chiroyli formatda qo'shish
                                topic_part = f"<b>Topic:</b><br/>{t_obj.topic} <br/><i>{t_obj.context_text}</i>"
                                if hasattr(t_obj, 'contextText') and t_obj.context_text:
                                    topic_part += f"<br/><i>{t_obj.context_text}</i>"
                                
                                topic_part += f"<br/><br/><b>Word Count:</b> Min: {t_obj.min_words} - Max: {t_obj.max_words}"
                                parts.append(topic_part)
                            
                            full_question_content = "<br/><br/>".join(parts) if parts else full_question_content
                            break

                # --- SAVOL MATNI BLOKINI QO'SHISH (Yopishib qolishni oldini olish bilan) ---

                # 1. Sarlavhadan oldin qo'shimcha bo'shliq
                elements.append(Spacer(1, 8*mm)) 

                # 2. "Full Question / Prompt" sarlavhasi
                elements.append(Paragraph("Full Question / Prompt:", label_style))

                # 3. Sarlavha va blok orasidagi kichik masofa
                elements.append(Spacer(1, 3*mm)) 

                # 4. Asosiy savol matni bloki (fondagi blok)
                # html.escape qilinganda bizga kerakli <b> va <br/> teglari buzilmasligi uchun ularni qayta tiklaymiz
                formatted_content = html.escape(full_question_content)\
                    .replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")\
                    .replace("&lt;br/&gt;", "<br/>").replace("&lt;i&gt;", "<i>").replace("&lt;/i&gt;", "</i>")

                elements.append(Paragraph(formatted_content, block_style))

                # 5. Blokdan keyin keladigan element (masalan, Student's Response) orasidagi masofa
                elements.append(Spacer(1, 10*mm))
                                
                # CRITERIA JADVALI
                crit = task_data.get("criteria", {})
                elements.append(Paragraph(f"Scoring Details (Task Score: {task_data.get('score', 0)})", label_style))
                crit_data = [
                    [Paragraph("<b>Criteria</b>", text_style), Paragraph("<b>Score (1-4)</b>", text_style)],
                    ["Task Achievement", crit.get("taskAchievement", 0)],
                    ["Coherence & Cohesion", crit.get("coherence", 0)],
                    ["Lexical Resource", crit.get("vocabulary", 0)],
                    ["Grammatical Range", crit.get("grammar", 0)]
                ]
                ct = Table(crit_data, colWidths=[100*mm, 40*mm])
                ct.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                ]))
                elements.append(ct)
                elements.append(Spacer(1, 10*mm)) # Jadvaldan keyin bo'shliq

                # FEEDBACK
                elements.append(Spacer(1, 8*mm)) 
                elements.append(Paragraph("AI Examiner Feedback:", label_style))
                feedback_txt = task_data.get('feedback', 'No feedback provided.')
                elements.append(Spacer(1, 8*mm)) 
                elements.append(Paragraph(f"<i>{html.escape(feedback_txt)}</i>", block_style))
                
                # SUGGESTIONS
                suggestions = task_data.get("suggestions", [])
                if suggestions:
                    elements.append(Spacer(1, 6*mm))
                    elements.append(Paragraph("Improvement Suggestions:", label_style))
                    for sug in suggestions:
                        elements.append(Paragraph(f"• {html.escape(sug)}", ParagraphStyle('Sug', parent=text_style, leftIndent=12, spaceBefore=2)))

            # 4. FOOTER
            elements.append(Spacer(1, 20*mm))
            elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
            footer_text = f"Report generated on {date_str} by cefr.enwis.uz AI Engine. BAA 2025 standard."
            elements.append(Paragraph(footer_text, ParagraphStyle('Footer', alignment=1, fontSize=8, textColor=colors.grey, spaceBefore=5)))

            doc.build(elements)
            buffer.seek(0)
            return buffer

        except Exception as e:
            logger.error(f"PDF Error: {str(e)}", exc_info=True)
            raise e