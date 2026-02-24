import asyncio
import json
import logging
import re
from typing import List, Dict, Any, Tuple

import httpx
from fastapi import HTTPException
from groq import AsyncGroq
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from ..models import (
    WritingAnswer,
    WritingCriterion,
    WritingExam,
    WritingFeedback,
    WritingResult,
    WritingScore,
    WritingTask,
    FeedbackSource,
)
from ..schemas import WritingAnswerSubmit

logger = logging.getLogger(__name__)

CRITERION_MAP = {
    "taskAchievement": WritingCriterion.TASK_ACHIEVEMENT,
    "coherence": WritingCriterion.COHERENCE,
    "vocabulary": WritingCriterion.VOCABULARY,
    "grammar": WritingCriterion.GRAMMAR,
}
REQUIRED_CRITERIA = {"taskAchievement", "coherence", "vocabulary", "grammar"}


# raw(1..16) -> base score tables (B2/C1 pdfga mos)
PART12_CONVERT_10 = {
    1: 0.6, 2: 1.3, 3: 1.9, 4: 2.5, 5: 3.1, 6: 3.8, 7: 4.4, 8: 5.0,
    9: 5.6, 10: 6.3, 11: 6.9, 12: 7.5, 13: 8.1, 14: 8.8, 15: 9.4, 16: 10.0
}
PART2_CONVERT_20 = {
    1: 1.3, 2: 2.5, 3: 3.8, 4: 5.0, 5: 6.3, 6: 7.5, 7: 8.8, 8: 10.0,
    9: 11.3, 10: 12.5, 11: 13.8, 12: 15.0, 13: 16.3, 14: 17.5, 15: 18.8, 16: 20.0
}

def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def count_words(text: str) -> int:
    if not text:
        return 0
    return len(re.findall(r"\b\w+(?:[-']\w+)*\b", text.strip()))


def word_penalty(task: WritingTask, wc: int) -> int:
    """
    Penalty qoidasi: task.format min/max bo'lsa ishlat.
    Yangi format uchun: min/max har taskga individual bo'lsa eng to'g'ri shu.
    """
    if not task.format:
        return 0

    min_w = int(task.format.min_words or 0)
    max_w = int(task.format.max_words or 10**9)

    # strict reject emas, penalty:
    if wc < min_w:
        return 1
    if wc > max_w:
        return 1
    return 0


class WritingSubmit:
    """
    New multilevel writing:
    - Task 1.1 => 12
    - Task 1.2 => 12
    - Task 2   => 24
    Total: 48 -> scaled 75 (temporary linear)
    Attempt limit: default 3
    """

    def __init__(
        self,
        db: AsyncSession,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        ai_timeout: int = 25,
        max_words: int = 2000,
        ai_concurrency: int = 3,
        attempt_limit: int = 3,
    ):
        if not api_key:
            raise ValueError("api_key is required")

        self.db = db
        self.client = AsyncGroq(api_key=api_key)
        self.model = model
        self.ai_timeout = ai_timeout
        self.max_words = max_words
        self.ai_semaphore = asyncio.Semaphore(ai_concurrency)
        self.attempt_limit = attempt_limit

    async def submit_exam(self, user_id: int, exam_id: str, answers: List[WritingAnswerSubmit]) -> WritingResult:
        if not answers:
            raise HTTPException(400, "No answers submitted")

        # duplicate task check
        ids = [a.task_id for a in answers]
        if len(ids) != len(set(ids)):
            raise HTTPException(400, "Duplicate task_id in payload")

        attempts = await self.db.scalar(
            select(func.count(WritingResult.id)).where(
                WritingResult.user_id == user_id,
                WritingResult.exam_id == exam_id,
            )
        )
        if int(attempts or 0) >= self.attempt_limit:
            raise HTTPException(429, f"Attempt limit reached (max {self.attempt_limit})")

        try:
            result_id = await self._process_submission(user_id, exam_id, answers)
            return await self._get_result(result_id)
        except IntegrityError as e:
            logger.exception("IntegrityError: %s", e)
            raise HTTPException(409, "Submission conflict")
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Submission failed: %s", e)
            raise HTTPException(500, "Writing evaluation failed")
        
    def _cefr_from_75(self, score75: int) -> str:
        s = int(score75)
        if s >= 70:
            return "C1"
        if s >= 50:
            return "B2"
        if s >= 38:
            return "B1"
        if s >= 21:
            return "A2"
        return "FAILED"

    async def _process_submission(self, user_id: int, exam_id: str, answers: List[WritingAnswerSubmit]) -> int:
        exam = await self.db.get(WritingExam, exam_id)
        if not exam:
            raise HTTPException(404, "Exam not found")

        submitted_ids = {a.task_id for a in answers}

        tasks = await self.db.scalars(
            select(WritingTask)
            .options(selectinload(WritingTask.format))
            .where(WritingTask.exam_id == exam_id, WritingTask.id.in_(submitted_ids))
        )
        tasks = list(tasks)

        if len(tasks) != len(submitted_ids):
            raise HTTPException(400, "Invalid task IDs")

        task_map = {t.id: t for t in tasks}

        processed: List[Tuple[WritingAnswerSubmit, WritingTask, int, Dict[str, Any], Dict[str, Any]]] = await asyncio.gather(
            *[self._evaluate_single(a, task_map) for a in answers]
        )

        result = WritingResult(
            user_id=user_id,
            exam_id=exam_id,
            raw_score=0.0,      # total48
            scaled_score=0.0,   # final75
            is_finalized=False,
        )
        self.db.add(result)
        await self.db.flush()

        total48 = 0.0
        for answer_input, task, wc, ai_result, scoring in processed:
            task_score = float(scoring["finalScore"])
            total48 += task_score

            answer_row = WritingAnswer(
                result_id=result.id,
                task_id=task.id,
                content=answer_input.content.strip(),
                word_count=wc,
                penalty=float(scoring.get("penalty", 0)),
                raw_score=float(scoring.get("rawScore", 0)),
                scaled_score=task_score,
            )
            self.db.add(answer_row)
            await self.db.flush()

            for key, value in (scoring.get("criteria") or {}).items():
                enum_val = CRITERION_MAP.get(key)
                if enum_val:
                    self.db.add(
                        WritingScore(
                            answer_id=answer_row.id,
                            criterion=enum_val,
                            score=float(value),
                        )
                    )

            fb = (ai_result or {}).get("feedback")
            if fb:
                self.db.add(
                    WritingFeedback(
                        answer_id=answer_row.id,
                        source=FeedbackSource.AI,
                        model_name=self.model,
                        content=str(fb).strip(),
                    )
                )

        # ✅ TEMP mapping: 0..48 -> 0..75
        final75 = round((clamp(total48, 0.0, 48.0) / 48.0) * 75.0)

        result.cefr_level = self._cefr_from_75(final75)   # ✅ SHU YO‘Q EDI
        result.raw_score = round(total48, 2)
        result.scaled_score = float(final75)
        result.is_finalized = True
        await self.db.flush()

        return result.id

    async def _evaluate_single(
        self,
        answer_input: WritingAnswerSubmit,
        task_map: Dict[int, WritingTask],
    ) -> Tuple[WritingAnswerSubmit, WritingTask, int, Dict[str, Any], Dict[str, Any]]:

        task = task_map.get(answer_input.task_id)
        if not task:
            raise HTTPException(400, "Invalid task")

        content = (answer_input.content or "").strip()
        if len(content) < 10:
            raise HTTPException(400, f"Task {task.part_number} text too short")

        wc = count_words(content)
        if wc > self.max_words:
            raise HTTPException(400, f"Task {task.part_number} text too long")

        penalty = word_penalty(task, wc)

        part_number = int(task.part_number)
        sub_part = None if task.sub_part is None else int(task.sub_part)

        task_type = "general"
        if task.format and getattr(task.format, "style", None):
            task_type = task.format.style.value

        async with self.ai_semaphore:
            try:
                ai_result = await asyncio.wait_for(
                    self._evaluate_ai(
                        topic=task.topic,
                        instruction=task.instruction,
                        user_text=content,
                        part_number=part_number,
                        task_type=task_type,
                    ),
                    timeout=self.ai_timeout,
                )
            except asyncio.TimeoutError:
                raise HTTPException(500, "AI evaluation timeout")

        scoring = self._calculate_score_new(
            ai_result=ai_result,
            part_number=part_number,
            sub_part=sub_part,
            penalty=penalty,
        )

        return answer_input, task, wc, ai_result, scoring

    async def _evaluate_ai(self, topic: str, instruction: str, user_text: str, part_number: int, task_type: str) -> Dict[str, Any]:
        system_prompt = self._build_prompt(topic, instruction, part_number, task_type)
        raw = await self._call_model(system_prompt, user_text)
        parsed = self._parse_json(raw)
        self._validate_ai(parsed)
        return parsed

    def _build_prompt(self, topic: str, instruction: str, part_number: int, task_type: str) -> str:
        return f"""
You are a certified CEFR writing examiner.

STRICT RULES:
- Use ONLY integer scores 1–4.
- Return STRICT JSON only.
- No markdown.
- No extra text.

PART: {part_number}
TASK TYPE: {task_type}
TOPIC: {topic}
INSTRUCTION: {instruction}

JSON format:
{{
  "criteria": {{
    "taskAchievement": 1,
    "coherence": 1,
    "vocabulary": 1,
    "grammar": 1
  }},
  "feedback": "Detailed feedback (min 20 chars).",
  "suggestions": ["Suggestion 1", "Suggestion 2", "Suggestion 3"]
}}
""".strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.HTTPError, TimeoutError)),
        reraise=True,
    )
    async def _call_model(self, system_prompt: str, user_text: str) -> str:
        try:
            resp = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    temperature=0.0,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_text},
                    ],
                ),
                timeout=self.ai_timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError("AI request timeout")

        if not resp or not resp.choices:
            raise ValueError("No AI response")

        content = resp.choices[0].message.content
        if not content:
            raise ValueError("Empty AI response")

        return content.strip()

    def _parse_json(self, raw: str) -> Dict[str, Any]:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"```json|```", "", cleaned).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                return json.loads(match.group())
        raise ValueError("Invalid JSON returned by AI")

    def _validate_ai(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            raise ValueError("Invalid AI structure")

        criteria = data.get("criteria")
        if not isinstance(criteria, dict):
            raise ValueError("Missing criteria")

        if set(criteria.keys()) != REQUIRED_CRITERIA:
            raise ValueError("Criteria keys mismatch")

        for v in criteria.values():
            if not isinstance(v, int) or not (1 <= v <= 4):
                raise ValueError("Score out of range")

        feedback = data.get("feedback")
        if not isinstance(feedback, str) or len(feedback.strip()) < 20:
            raise ValueError("Invalid feedback")

        suggestions = data.get("suggestions")
        if not isinstance(suggestions, list) or len(suggestions) < 3:
            raise ValueError("At least 3 suggestions required")

    def _calculate_score_new(self, ai_result: Dict[str, Any], part_number: int, sub_part: int | None, penalty: int) -> Dict[str, Any]:
        criteria: Dict[str, int] = ai_result["criteria"]
        raw = int(sum(criteria.values()))  # 4..16

        # ✅ Part 1 has two tasks: 1.1 and 1.2 -> each to 12
        if part_number == 1:
            base10 = float(PART12_CONVERT_10.get(raw, 0.6))
            base12 = base10 * 1.2   # 12 scale
            base = base12

        # ✅ Part 2 -> 24
        elif part_number == 2:
            base20 = float(PART2_CONVERT_20.get(raw, 1.3))
            base24 = base20 * 1.2   # 24 scale
            base = base24

        else:
            raise ValueError(f"Unsupported part_number={part_number}")

        final = max(base - float(penalty), 0.0)

        return {
            "rawScore": raw,
            "finalScore": round(final, 2),
            "penalty": penalty,
            "criteria": criteria,
        }

    async def _get_result(self, result_id: int) -> WritingResult:
        stmt = (
            select(WritingResult)
            .where(WritingResult.id == result_id)
            .options(
                selectinload(WritingResult.answers).selectinload(WritingAnswer.scores),
                selectinload(WritingResult.answers).selectinload(WritingAnswer.feedbacks),
            )
        )
        res = await self.db.execute(stmt)
        return res.scalar_one()