from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from app.modules.auth.models import User

from ..models import (
    WritingResult,
    WritingAnswer,
)


class WritingResultService:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================================================
    # SINGLE EXAM RESULT
    # ==================================================

    async def get_exam_result(
        self,
        user_id: int,
        exam_id: str,
    ) -> WritingResult:

        result = await self.db.scalar(
            select(WritingResult)
            .options(
                selectinload(WritingResult.answers)
                .selectinload(WritingAnswer.scores)
            )
            .where(
                WritingResult.user_id == user_id,
                WritingResult.exam_id == exam_id,
            )
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Result not found",
            )

        # Agar future’da background scoring bo‘lsa
        if not result.is_finalized:
            raise HTTPException(
                status_code=status.HTTP_202_ACCEPTED,
                detail="Result is still being processed",
            )

        return result

    # ==================================================
    # USER ALL RESULTS
    # ==================================================

    async def get_user_results(
        self,
        user_id: int,
    ) -> list[WritingResult]:

        results = await self.db.scalars(
            select(WritingResult)
            .options(
                selectinload(WritingResult.answers)
            )
            .where(WritingResult.user_id == user_id)
            .order_by(WritingResult.created_at.desc())
        )

        return list(results)

    # ==================================================
    # ADMIN: GET ALL RESULTS
    # ==================================================

    async def get_all_results(self) -> list[WritingResult]:

        results = await self.db.scalars(
            select(WritingResult)
            .options(
                selectinload(WritingResult.answers)
            )
            .order_by(WritingResult.created_at.desc())
        )

        return list(results)

    # ==================================================
    # GET BY RESULT ID
    # ==================================================

    async def get_result_by_id(
        self,
        result_id: int,
    ) -> WritingResult:

        result = await self.db.scalar(
            select(WritingResult)
            .options(
                selectinload(WritingResult.answers)
                .selectinload(WritingAnswer.scores)
            )
            .where(WritingResult.id == result_id)
        )

        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Result not found",
            )

        return result
    
    async def get_result_full_for_pdf(self, result_id: int) -> WritingResult | None:
        stmt = (
            select(WritingResult)
            .where(WritingResult.id == result_id)
            .options(
                selectinload(WritingResult.exam),

                # ✅ user + profile + contacts
                selectinload(WritingResult.user).selectinload(User.profile),
                selectinload(WritingResult.user).selectinload(User.contacts),

                # ✅ answers -> task + scores + feedbacks
                selectinload(WritingResult.answers).selectinload(WritingAnswer.task),
                selectinload(WritingResult.answers).selectinload(WritingAnswer.scores),
                selectinload(WritingResult.answers).selectinload(WritingAnswer.feedbacks),
            )
        )
        return await self.db.scalar(stmt)