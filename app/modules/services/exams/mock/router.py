from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from . import schemas, services, models

router = APIRouter(
    prefix="/mock-exams", 
    tags=["CEFR Multilevel Mock Exams"]
)

# --- 1. ADMIN CRUD (Imtihonlarni boshqarish) ---

@router.post("/create", response_model=schemas.UserMockExamResponse, status_code=status.HTTP_201_CREATED)
async def admin_create_mock_exam(
    data: schemas.MockExamCreate, 
    db: AsyncSession = Depends(get_db)
):
    """
    Yangi Mock imtihonini tizimga qo'shish. 
    Reading va Listening testlari avtomatik tanlanadi.
    """
    return await services.create_exam(db, data)

@router.get("/get_all", response_model=List[schemas.UserMockExamResponse])
async def list_all_mock_exams(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Admin → barcha imtihonlar
    Oddiy user → faqat ruxsat berilgan va sotib olingan imtihonlar
    """
    if user.is_admin:  # User modelida admin flag bo'lishi kerak
        return await services.get_all_exams_admin(db)
    return await services.list_user_exams(db, user.id)


@router.put("/update/{exam_id}", response_model=schemas.UserMockExamResponse)
async def admin_update_mock_exam(
    exam_id: str,
    data: schemas.MockExamUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Mavjud imtihon ma'lumotlarini (narxi, test IDlari) tahrirlash."""
    return await services.update_exam(db, exam_id, data)

@router.delete("/delete/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
async def admin_delete_mock_exam(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Imtihonni tizimdan butunlay o'chirish."""
    await services.delete_exam_service(db, exam_id)
    return None


# --- 2. USER PROCESS (Imtihon topshirish jarayoni) ---

@router.get("/my-exams", response_model=List[schemas.UserMockExamResponse])
async def get_my_mock_exams(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Foydalanuvchi sotib olgan va ruxsati bor imtihonlar ro'yxati."""
    return await services.list_user_exams(db, user.id)

@router.post("/mock/{exam_id}/start", response_model=schemas.MockExamStartResponse)
async def start_mock_exam_process(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user),
):
    """Imtihon sessiyasini (attempt) boshlash."""
    return await services.start_exam(db, user.id, exam_id)

@router.get("/attempts/{attempt_id}/status", response_model=List[schemas.MockSkillStatusResponse])
async def get_mock_status(
    attempt_id: int, 
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Qaysi bo'limlar topshirilganini (is_checked) tekshirish."""
    # User ownership tekshiruvi
    attempt_stmt = await db.get(models.MockExamAttempt, attempt_id)
    if not attempt_stmt or attempt_stmt.user_id != user.id:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")

    status_data = await services.get_attempt_status_service(db, attempt_id)
    return status_data

@router.post("/attempts/{attempt_id}/submit/{skill}", response_model=schemas.MockSkillAttemptResponse)
async def submit_skill_progress(
    attempt_id: int,
    skill: models.SkillType,
    data: schemas.MockSkillSubmit,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """
    Bo'limni topshirish. Reading va Listening bo'lsa backendda avtomatik tekshiriladi.
    Natija Rasch metodi asosida hisoblanadi.
    """
    # Ownership tekshiruv
    attempt = await db.get(models.MockExamAttempt, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")
    return await services.submit_skill(db, attempt_id, skill, data)

@router.post("/attempts/{attempt_id}/finish", response_model=schemas.MockExamResultResponse)
async def finish_mock_exam_process(
    attempt_id: int,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """4 ta skill bitganini tekshirib, yakuniy CEFR darajasini aniqlash."""
    attempt = await db.get(models.MockExamAttempt, attempt_id)
    if not attempt or attempt.user_id != user.id:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")
    return await services.finish_exam_service(db, attempt_id)

@router.post("/{exam_id}/buy", status_code=status.HTTP_201_CREATED)
async def buy_mock_exam(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Imtihonni sotib olish so'rovini yuborish."""
    await services.buy_exam_request(db, user.id, exam_id)
    return {"message": "To'lov so'rovi yuborildi. Admin tasdiqlashini kuting."}

@router.get("/results/history", response_model=List[schemas.MockExamResultResponse])
async def get_my_results_history(
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Foydalanuvchining barcha topshirgan imtihonlari tarixi."""
    return await services.get_user_results_history(db, user.id)

@router.get("/attempts/{attempt_id}/result", response_model=schemas.MockExamResultResponse)
async def get_specific_result(
    attempt_id: int,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user)
):
    """Muayyan imtihon natijasini olish (PDF yoki Grafika uchun)."""
    result = await services.get_mock_result_service(db, attempt_id)
    if result.user_id != user.id:
        raise HTTPException(status_code=403, detail="Ruxsat berilmagan")
    return result
