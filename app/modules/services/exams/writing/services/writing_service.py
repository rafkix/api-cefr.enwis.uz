from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings

from .admin_service import WritingAdminService
from .submission_service import WritingSubmit
from .result_service import WritingResultService
from .pdf_service import PDFService


class WritingService:
    """
    Facade layer for CEFR Writing module.

    Responsible for:
    - Exam management
    - Submission processing
    - Result retrieval
    - PDF generation
    """

    def __init__(self, db: AsyncSession):
        self.db = db

        # Core services
        self.admin_service = WritingAdminService(db)
        self.result_service = WritingResultService(db)

        # Submission service (AI + scoring inside)
        self.submission_service = WritingSubmit(
            db=db,
            api_key=settings.API_KEY_GROK,
        )

        self.pdf_service = PDFService()

    # =====================================================
    # EXAMS
    # =====================================================

    async def create_exam(self, data):
        return await self.admin_service.create_exam(data)

    async def list_exams(self):
        return await self.admin_service.list_exams()

    async def get_exam(self, exam_id: str):
        return await self.admin_service.get_exam_by_id(exam_id)

    async def update_exam(self, exam_id: str, data):
        return await self.admin_service.update_exam(exam_id, data)

    async def delete_exam(self, exam_id: str):
        return await self.admin_service.delete_exam(exam_id)

    # =====================================================
    # SUBMISSION
    # =====================================================

    async def submit_exam(self, user_id: int, exam_id: str, answers):
        return await self.submission_service.submit_exam(
            user_id=user_id,
            exam_id=exam_id,
            answers=answers,
        )

    # =====================================================
    # RESULTS
    # =====================================================

    async def get_user_results(self, user_id: int):
        return await self.result_service.get_user_results(user_id)

    async def get_all_results(self):
        return await self.result_service.get_all_results()

    async def get_result(self, result_id: int):
        return await self.result_service.get_result_by_id(result_id)

    # =====================================================
    # PDF
    # =====================================================

    async def generate_pdf_report(self, result_id: int):
        result = await self.result_service.get_result_by_id(result_id)

        if not result:
            raise ValueError("Result not found")

        return await self.pdf_service.generate_pdf_report(result=result_id)