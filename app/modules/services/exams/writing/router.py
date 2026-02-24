from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from sqlalchemy.orm import selectinload
from app.core.database import get_db

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.models import User, UserRole

from app.modules.services.exams.writing.models import WritingAnswer, WritingResult
from app.modules.services.exams.writing.services.pdf_service import PDFService
from app.modules.services.exams.writing.services.submission_service import WritingSubmit
from .schemas import (
    WritingExamCreate,
    WritingExamRead,
    WritingExamUpdate,
    WritingSubmitRequest,
    WritingResultRead,
)
from .services import WritingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/cefr/all/writing",
    tags=["Writing"],
)

# ---------------------------
# DI
# ---------------------------

def get_writing_service(db: AsyncSession = Depends(get_db)) -> WritingService:
    return WritingService(db)

# ---------------------------
# Helpers
# ---------------------------

_PROMPT_RE = re.compile(
    r"(Task\s+1\.1|Task\s+1\.2|Part\s+1|Part\s+2|Limit:\s*\d+|\bWrite\b\s+\d+\s*-\s*\d+\s+words)",
    re.IGNORECASE,
)

def _is_admin(user: User) -> bool:
    # projectda qaysi biri asosiy bo'lsa, shuni qoldirasan
    if hasattr(user, "is_admin") and bool(getattr(user, "is_admin")):
        return True
    if hasattr(user, "global_role") and getattr(user, "global_role") == UserRole.ADMIN:
        return True
    return False

def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

def _validate_submit_payload(payload: WritingSubmitRequest) -> None:
    if not payload.answers or not isinstance(payload.answers, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="answers is required",
        )

    for a in payload.answers:
        # task_id must be int
        if a.task_id is None or not isinstance(a.task_id, int):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Each answer must have integer task_id",
            )
        # content basic validation
        content = (a.content or "").strip()
        if len(content) < 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Task {a.task_id}: content too short (min 10 chars)",
            )
        # your real bug: prompt text being sent
        if _PROMPT_RE.search(content):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Task {a.task_id}: looks like prompt/instructions, not a user answer",
            )

# ---------------------------
# Admin CRUD
# ---------------------------

@router.post("/create", response_model=WritingExamRead, status_code=status.HTTP_201_CREATED)
async def create_exam(
    data: WritingExamCreate,
    current_user: User = Depends(get_current_user),
    service: WritingService = Depends(get_writing_service),
):
    _require_admin(current_user)
    return await service.create_exam(data)

@router.put("/update/{exam_id}", response_model=WritingExamRead)
async def update_exam(
    exam_id: str,
    data: WritingExamUpdate,
    current_user: User = Depends(get_current_user),
    service: WritingService = Depends(get_writing_service),
):
    _require_admin(current_user)

    updated = await service.update_exam(exam_id, data)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    return updated

@router.delete("/delete/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: str,
    current_user: User = Depends(get_current_user),
    service: WritingService = Depends(get_writing_service),
):
    _require_admin(current_user)

    deleted = await service.delete_exam(exam_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    # 204 => body bo'lmasin
    return Response(status_code=status.HTTP_204_NO_CONTENT)

# ---------------------------
# Public / user
# ---------------------------

@router.get("/get_all", response_model=List[WritingExamRead])
async def get_exams(service: WritingService = Depends(get_writing_service)):
    return await service.list_exams()

@router.get("/get/{exam_id}", response_model=WritingExamRead)
async def get_exam(exam_id: str, service: WritingService = Depends(get_writing_service)):
    exam = await service.get_exam(exam_id)
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")
    return exam

@router.get("/my-results/all", response_model=List[WritingResultRead])
async def get_my_results(
    current_user: User = Depends(get_current_user),
    service: WritingService = Depends(get_writing_service),
):
    return await service.get_user_results(current_user.id)

@router.get("/results/{result_id}", response_model=WritingResultRead)
async def get_result(
    result_id: int,
    current_user: User = Depends(get_current_user),
    service: WritingService = Depends(get_writing_service),
):
    result = await service.get_result(result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    if result.user_id != current_user.id and not _is_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    return result

@router.get("/results/{result_id}/pdf")
async def export_result_pdf(result_id: int, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(WritingResult)
        .where(WritingResult.id == result_id)
        .options(
            selectinload(WritingResult.exam),

            # ✅ user -> profile
            selectinload(WritingResult.user).selectinload(User.profile),

            # ✅ answers
            selectinload(WritingResult.answers).selectinload(WritingAnswer.task),
            selectinload(WritingResult.answers).selectinload(WritingAnswer.scores),
            selectinload(WritingResult.answers).selectinload(WritingAnswer.feedbacks),
        )
    )

    res = await db.execute(stmt)
    result = res.scalar_one_or_none()
    if not result:
        raise HTTPException(404, "Result not found")

    # DEBUG
    print("RESULT:", result.id, "ANSWERS:", len(result.answers or []))

    pdf_bytes = await PDFService().generate_pdf_report(result)

    filename = f'writing-{datetime.utcnow().strftime("%Y%m%d-%H%M")}-result{result_id}.pdf'
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# ---------------------------
# Submit
# ---------------------------

@router.post("/exams/{exam_id}/submit", response_model=WritingResultRead)
async def submit_exam(
    request: Request,
    exam_id: str,
    payload: WritingSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ✅ To'g'ri loglar
    logger.info("SUBMIT exam_id=%s user_id=%s", exam_id, current_user.id)
    logger.debug("SUBMIT payload=%s", payload.model_dump())

    # ✅ Basic payload validation
    _validate_submit_payload(payload)

    service = WritingSubmit(db=db, api_key=settings.API_KEY_GROK)

    try:
        result = await service.submit_exam(current_user.id, exam_id, payload.answers)
        await db.commit()
        return result
    except HTTPException as e:
        # ✅ service ichidagi 400/409/422 detailni ko'rsat
        logger.warning("SUBMIT failed status=%s detail=%s", e.status_code, e.detail)
        raise
    except Exception as e:
        logger.exception("SUBMIT unexpected error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal server error") from e