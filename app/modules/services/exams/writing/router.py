from datetime import datetime
import logging
from annotated_types import T
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List


# Ichki modullardan importlar
from app.core.database import get_db
from .services import WritingService
from .schemas import (
    WritingExamCreate, WritingExamUpdate, WritingExamResponse,
    WritingSubmission, WritingResultResponse
)

router = APIRouter(prefix="/cefr/all/writing", tags=["Writing Exam System"])

# ================================================================
# 1. EXAM MANAGEMENT (Admin va User uchun)
# ================================================================

@router.post("/create", response_model=WritingExamResponse, status_code=status.HTTP_201_CREATED)
async def create_new_exam(data: WritingExamCreate, db: AsyncSession = Depends(get_db)):
    """Yangi imtihon va tasklarni yaratish (Admin)"""
    service = WritingService(db)
    return await service.create_exam(data)

@router.get("/get_all", response_model=List[WritingExamResponse])
async def get_all_exams(db: AsyncSession = Depends(get_db)):
    """Barcha imtihonlar ro'yxatini olish"""
    service = WritingService(db)
    return await service.get_all_exams()

@router.get("/get/{exam_id}", response_model=WritingExamResponse)
async def get_exam(exam_id: str, db: AsyncSession = Depends(get_db)):
    """ID bo'yicha bitta imtihonni olish"""
    service = WritingService(db)
    return await service.get_exam_by_id(exam_id)

@router.patch("/update/{exam_id}", response_model=WritingExamResponse)
async def update_exam(exam_id: str, data: WritingExamUpdate, db: AsyncSession = Depends(get_db)):
    """Imtihon ma'lumotlarini yoki tasklarini yangilash"""
    service = WritingService(db)
    return await service.update_exam(exam_id, data)

@router.delete("/delete/{exam_id}")
async def delete_exam(exam_id: str, db: AsyncSession = Depends(get_db)):
    """Imtihonni o'chirish"""
    service = WritingService(db)
    return await service.delete_exam(exam_id)

# ================================================================
# 2. SUBMISSION & RESULTS (Natijalar bilan ishlash)
# ================================================================

@router.post("/submit", response_model=WritingResultResponse)
async def submit_writing_exam(
    data: WritingSubmission, 
    user_id: int, # Haqiqiy loyihada current_user dan olinadi
    db: AsyncSession = Depends(get_db)
):
    """
    Foydalanuvchi javoblarini topshirish va AI bahosini olish.
    Response WritingResultResponse sxemasi asosida qaytadi (matnlar bilan birga).
    """
    service = WritingService(db)
    return await service.submit_exam_with_ai(user_id=user_id, data=data)

@router.get("/results/user/{user_id}", response_model=List[WritingResultResponse])
async def get_my_results(user_id: int, db: AsyncSession = Depends(get_db)):
    """Foydalanuvchining barcha topshirgan ishlari tarixi"""
    service = WritingService(db)
    return await service.get_user_results(user_id)

@router.get("/my-results/all", response_model=List[WritingResultResponse])
async def get_all_user_results(db: AsyncSession = Depends(get_db)):
    """Barcha foydalanuvchilarning natijalari (Admin uchun)"""
    service = WritingService(db)
    return await service.get_all_results()

@router.get("/results/{result_id}", response_model=WritingResultResponse)
async def get_single_result(result_id: int, db: AsyncSession = Depends(get_db)):
    """ID bo'yicha aniq bir natijani (yozilgan matn va AI feedback) ko'rish"""
    service = WritingService(db)
    return await service.get_result_by_id(result_id)

@router.get("/results/{result_id}/download-pdf")
async def download_writing_pdf(
    result_id: int, 
    db: AsyncSession = Depends(get_db)
):
    service = WritingService(db)
    try:
        # 1. Endi bu yerda result.exam ham tayyor holda keladi
        result = await service.get_result_by_id(result_id=result_id)
        
        # 2. PDF generatsiya
        pdf_buffer = await service.generate_pdf_report(result)
        
        # 3. Fayl nomiga sana va user_id qo'shish
        current_date = datetime.now().strftime("%Y-%m-%d")
        user_id = result.user_id if result.user_id else "unknown"
        filename = f"writing_User{user_id}_{current_date}_result{result.id}.pdf"
        
        return StreamingResponse(
            pdf_buffer, 
            media_type="application/pdf", 
            headers={
                # Chrome tabida ochish uchun 'inline' qoldirdim
                "Content-Disposition": f'inline; filename="{filename}"',
                "Access-Control-Expose-Headers": "Content-Disposition"
            }
        )
    except Exception as e:
        logging.error(f"PDF Error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"PDF yaratishda xatolik: {str(e)}"
        )