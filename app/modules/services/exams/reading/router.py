from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user, require_role
from app.modules.auth.models import User

# Service & Schemas
from .services import ReadingService
from .schemas import (
    ReadingTestCreate,
    ReadingTestUpdate,
    ReadingTestResponse,
    ReadingSubmitRequest,
    ReadingResultResponse,
    ReadingResultDetailResponse,
)

router = APIRouter(
    prefix="/cefr/all/reading",
    tags=["CEFR Reading"],
)

# =================================================================
#  1. CREATE (YARATISH) - ADMIN ONLY
# =================================================================
@router.post(
    "/create",
    response_model=ReadingTestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role)],
)
async def create_reading_test(
    data: ReadingTestCreate,
    db: AsyncSession = Depends(get_db),
):
    """Yangi Reading test yaratish"""
    service = ReadingService(db)
    return await service.create_test(data)


# =================================================================
#  2. READ (O'QISH) - PUBLIC
# =================================================================
@router.get(
    "/get_all",
    response_model=List[ReadingTestResponse],
)
async def get_all_reading_tests(
    db: AsyncSession = Depends(get_db),
):
    """Barcha faol Reading testlar ro'yxati"""
    service = ReadingService(db)
    return await service.get_all_tests()


@router.get(
    "/get/{test_id}",
    response_model=ReadingTestResponse,
)
async def get_reading_test(
    test_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Testni ishlash uchun to'liq ma'lumotlari bilan olish"""
    service = ReadingService(db)
    test = await service.get_test_by_id(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Reading test topilmadi")
    return test


# =================================================================
#  3. UPDATE (YANGILASH) - ADMIN ONLY
# =================================================================
@router.put(
    "/update/{test_id}",
    response_model=ReadingTestResponse,
    dependencies=[Depends(require_role)],
)
async def update_reading_test(
    test_id: str,
    data: ReadingTestUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Test ma'lumotlarini yangilash"""
    service = ReadingService(db)
    return await service.update_test(test_id, data)


# =================================================================
#  4. DELETE (O'CHIRISH) - ADMIN ONLY
# =================================================================
@router.delete(
    "/delete/{test_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_role)],
)
async def delete_reading_test(
    test_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Testni o'chirish"""
    service = ReadingService(db)
    success = await service.delete_test(test_id)
    if not success:
        raise HTTPException(status_code=404, detail="Test topilmadi")


# =================================================================
#  5. ACTIONS (JAVOB BERISH VA NATIJALAR) - AUTHENTICATED USER
# =================================================================
@router.post(
    "/answer/{test_id}/submit",
    response_model=ReadingResultDetailResponse,
)
async def submit_reading_answers(
    test_id: str,
    data: ReadingSubmitRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Javoblarni yuborish.
    Agar 'exam_attempt_id' yuborilsa, Mock Exam tizimiga ulanadi.
    """
    service = ReadingService(db)
    return await service.submit_answers(
        user_id=user.id,
        test_id=test_id,
        data=data,
    )


@router.get(
    "/my-results/all",
    response_model=List[ReadingResultResponse],
)
async def get_my_reading_results(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Foydalanuvchining shaxsiy Reading natijalari tarixi"""
    service = ReadingService(db)
    return await service.get_user_results(user.id)


@router.get(
    "/results/{result_id}",
    response_model=ReadingResultDetailResponse,
)
async def get_reading_result_detail(
    result_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Natija tahlili (Review). 
    Faqat o'zining natijasini ko'ra oladi.
    """
    service = ReadingService(db)
    result = await service.get_result_with_review(result_id, user.id)
    
    if not result:
        raise HTTPException(status_code=404, detail="Natija topilmadi yoki ruxsat yo'q")
        
    return result