from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Any

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from .services import WritingService
from .schemas import (
    WritingExamCreate, WritingExamUpdate, WritingExamResponse,
    WritingSubmission, WritingResultResponse, WritingResultDetailResponse
)

router = APIRouter(prefix="/services/cefr/writing", tags=["CEFR Writing"])

def check_admin(user):
    if getattr(user, "role", "student") != "admin":
        raise HTTPException(403, "Admin access required")

# --- ADMIN ---
@router.post("/create", response_model=WritingExamResponse)
async def create(data: WritingExamCreate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    check_admin(user)
    return await WritingService(db).create_exam(data)

@router.put("/update/{id}", response_model=WritingExamResponse)
async def update(id: str, data: WritingExamUpdate, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    check_admin(user)
    return await WritingService(db).update_exam(id, data)

@router.delete("/delete/{id}")
async def delete(id: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    check_admin(user)
    return await WritingService(db).delete_exam(id)

# --- USER ---
@router.get("/list", response_model=List[WritingExamResponse])
async def list_exams(db: AsyncSession = Depends(get_db)):
    return await WritingService(db).get_all_exams()

@router.get("/{id}", response_model=WritingExamResponse)
async def get_exam(id: str, db: AsyncSession = Depends(get_db)):
    return await WritingService(db).get_exam_by_id(id)

@router.post("/submit", response_model=WritingResultDetailResponse)
async def submit(data: WritingSubmission, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return await WritingService(db).submit_exam_with_ai(user.id, data)

@router.get("/results/my", response_model=List[WritingResultResponse])
async def my_results(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    return await WritingService(db).get_user_results(user.id)

@router.get("/results/{id}", response_model=WritingResultDetailResponse)
async def result_detail(id: int, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    res = await WritingService(db).get_result_detail(id, user.id)
    if not res: raise HTTPException(404, "Not found")
    return res