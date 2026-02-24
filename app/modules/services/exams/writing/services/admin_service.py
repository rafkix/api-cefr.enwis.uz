import logging
from datetime import datetime
from typing import List

from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from fastapi import HTTPException

from ..models import (
    WritingExam,
    WritingFormat,
    WritingTask,
    WritingResult,
)
from ..schemas import WritingExamCreate, WritingExamUpdate

logger = logging.getLogger(__name__)


class WritingAdminService:

    MAX_ID_RETRY = 5

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==========================================================
    # INTERNAL
    # ==========================================================

    async def _generate_exam_identity(self) -> tuple[str, int, int]:
        current_year = datetime.utcnow().year

        result = await self.db.execute(
            select(func.max(WritingExam.sequence_number))
            .where(WritingExam.year == current_year)
        )

        last_sequence = result.scalar() or 0
        new_sequence = last_sequence + 1

        exam_id = f"writing-exams-{current_year}-{new_sequence:03d}"

        return exam_id, current_year, new_sequence

    async def _validate_formats(self, tasks):
        format_ids = {t.format_id for t in tasks}

        if not format_ids:
            raise HTTPException(400, "No format_id provided")

        result = await self.db.execute(
            select(WritingFormat.id)
            .where(WritingFormat.id.in_(format_ids))
        )

        found_ids = set(result.scalars().all())

        if format_ids != found_ids:
            raise HTTPException(400, "Invalid format_id provided")

    async def _has_results(self, exam_id: str) -> bool:
        result = await self.db.execute(
            select(func.count())
            .select_from(WritingResult)
            .where(WritingResult.exam_id == exam_id)
        )
        return result.scalar_one() > 0

    async def _get_exam_or_404(self, exam_id: str) -> WritingExam:
        result = await self.db.execute(
            select(WritingExam)
            .where(WritingExam.id == exam_id)
        )
        exam = result.scalar_one_or_none()

        if not exam:
            raise HTTPException(404, "Exam not found")

        return exam

    # ==========================================================
    # CREATE
    # ==========================================================

    async def create_exam(self, data: WritingExamCreate) -> WritingExam:

        await self._validate_formats(data.tasks)

        for attempt in range(self.MAX_ID_RETRY):

            exam_id, year, sequence_number = \
                await self._generate_exam_identity()

            exam = WritingExam(
                id=exam_id,
                year=year,
                sequence_number=sequence_number,
                title=data.title,
                cefr_level=data.cefr_level,
                duration_minutes=data.duration_minutes,
                is_demo=data.is_demo,
                is_free=data.is_free,
                is_mock=data.is_mock,
                is_active=data.is_active,
            )

            self.db.add(exam)

            try:
                await self.db.flush()
                break
            except IntegrityError:
                await self.db.rollback()
                logger.warning(
                    f"Exam ID conflict retry {attempt + 1}"
                )
        else:
            raise HTTPException(
                500,
                "Failed to generate unique exam ID"
            )

        tasks = [
            WritingTask(
                exam_id=exam.id,
                part_number=t.part_number,
                sub_part=t.sub_part,
                topic=t.topic,
                instruction=t.instruction,
                context_text=t.context_text,
                format_id=t.format_id,
            )
            for t in data.tasks
        ]

        self.db.add_all(tasks)

        await self.db.flush()

        return await self.get_exam_by_id(exam.id)

    # ==========================================================
    # READ
    # ==========================================================

    async def get_exam_by_id(self, exam_id: str) -> WritingExam:

        stmt = (
            select(WritingExam)
            .where(WritingExam.id == exam_id)
            .options(
                selectinload(WritingExam.tasks)
                .selectinload(WritingTask.format)
            )
        )

        result = await self.db.execute(stmt)
        exam = result.scalar_one_or_none()

        if not exam:
            raise HTTPException(404, "Exam not found")

        return exam

    async def list_exams(
        self,
        active_only: bool = False
    ) -> List[WritingExam]:

        stmt = select(WritingExam).options(
            selectinload(WritingExam.tasks)
            .selectinload(WritingTask.format)
        )

        if active_only:
            stmt = stmt.where(WritingExam.is_active.is_(True))

        result = await self.db.execute(stmt)

        return list(result.scalars().unique().all())

    # ==========================================================
    # UPDATE
    # ==========================================================

    async def update_exam(
        self,
        exam_id: str,
        data: WritingExamUpdate
    ) -> WritingExam:

        if await self._has_results(exam_id):
            raise HTTPException(
                400,
                "Cannot update exam with existing submissions"
            )

        exam = await self._get_exam_or_404(exam_id)

        update_data = data.model_dump(
            exclude_unset=True,
            exclude={"tasks"}
        )

        for field, value in update_data.items():
            setattr(exam, field, value)

        if data.tasks is not None:

            await self._validate_formats(data.tasks)

            await self.db.execute(
                delete(WritingTask)
                .where(WritingTask.exam_id == exam_id)
            )

            new_tasks = [
                WritingTask(
                    exam_id=exam.id,
                    part_number=t.part_number,
                    sub_part=t.sub_part,
                    topic=t.topic,
                    instruction=t.instruction,
                    context_text=t.context_text,
                    format_id=t.format_id,
                )
                for t in data.tasks
            ]

            self.db.add_all(new_tasks)

        await self.db.flush()

        return await self.get_exam_by_id(exam_id)

    # ==========================================================
    # DELETE
    # ==========================================================

    async def delete_exam(self, exam_id: str):

        if await self._has_results(exam_id):
            raise HTTPException(
                400,
                "Cannot delete exam with submissions"
            )

        exam = await self._get_exam_or_404(exam_id)
        await self.db.delete(exam)

        await self.db.flush()

        return {"status": "deleted"}