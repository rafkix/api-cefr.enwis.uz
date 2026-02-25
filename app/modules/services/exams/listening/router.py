from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User

# Servis va Sxemalar
from .services import ListeningService
from .schemas import (
    ListeningExamResponse, 
    ListeningExamCreate, 
    ListeningExamUpdate,
    ListeningResultResponse,
    ListeningSubmission,
    ListeningResultDetailResponse
)

router = APIRouter(
    prefix="/cefr/all/listening", 
    tags=["CEFR Listening"]
)


@router.post(
    "/create", 
    response_model=ListeningExamResponse, 
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role)]
)
async def create_listening_exam(
    data: ListeningExamCreate, 
    db: AsyncSession = Depends(get_db)
):
    """Yangi Listening imtihoni yaratish"""
    service = ListeningService(db)
    return await service.create_exam(data)


@router.get("/get_all", response_model=List[ListeningExamResponse])
async def get_all_listening_tests(db: AsyncSession = Depends(get_db)):
    """Barcha faol imtihonlar ro'yxati"""
    service = ListeningService(db)
    return await service.get_all_exams()


@router.get("/get/{exam_id}", response_model=ListeningExamResponse)
async def get_listening_test(exam_id: str, db: AsyncSession = Depends(get_db)):
    """Imtihon detallari va savollari (Testni boshlash uchun)"""
    service = ListeningService(db)
    exam = await service.get_exam_by_id(exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Listening test topilmadi")
    return exam


@router.put(
    "/update/{exam_id}", 
    response_model=ListeningExamResponse,
    dependencies=[Depends(require_role)]
)
async def update_listening_exam(
    exam_id: str, 
    data: ListeningExamUpdate, 
    db: AsyncSession = Depends(get_db)
):
    """Imtihon ma'lumotlarini yangilash"""
    service = ListeningService(db)
    return await service.update_exam(exam_id, data)


@router.delete(
    "/delete/{exam_id}", 
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role)]
)
async def delete_listening_exam(
    exam_id: str, 
    db: AsyncSession = Depends(get_db)
):
    """Imtihonni o'chirish"""
    service = ListeningService(db)
    success = await service.delete_exam(exam_id)
    if not success:
        raise HTTPException(404, detail="Imtihon topilmadi")


@router.post("/answer/submit", response_model=ListeningResultDetailResponse)
async def submit_listening_answers(
    submission: ListeningSubmission, 
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Javoblarni yuborish va natijani olish. 
    Mock Exam tizimiga ulash uchun 'exam_attempt_id' yuborish mumkin.
    """
    service = ListeningService(db)
    return await service.submit_exam_and_get_result(
        user_id=user.id, 
        data=submission
    )


@router.get("/my-results/all", response_model=List[ListeningResultResponse])
async def get_my_listening_results(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Foydalanuvchining shaxsiy natijalari tarixi"""
    service = ListeningService(db)
    return await service.get_user_results(user.id)


@router.get("/my-results/{result_id}", response_model=ListeningResultDetailResponse)
async def get_listening_result_detail(
    result_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Natija tahlili (Review). 
    Faqat o'zining natijasini ko'ra oladi.
    """
    service = ListeningService(db)
    result = await service.get_result_with_review(result_id, user.id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Natija topilmadi yoki ruxsat yo'q")
        
    return result