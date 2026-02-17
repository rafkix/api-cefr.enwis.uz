import enum
from sqlalchemy import (
    JSON, Column, DateTime, Float, Integer, String, Text, Enum, ForeignKey, Boolean, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base

# --- ENUMS ---
class WritingTaskType(str, enum.Enum):
    TASK_1_1_INFORMAL = "TASK_1_1_INFORMAL"
    TASK_1_2_FORMAL = "TASK_1_2_FORMAL"
    TASK_2_ESSAY = "TASK_2_ESSAY"

# --- WRITING EXAM (Test Shablonlari) ---
class WritingExam(Base):
    __tablename__ = "writing_exams"

    id = Column(String, primary_key=True, index=True) # Slug: "writing-test-1"
    title = Column(String, nullable=False)
    cefr_level = Column(String, default="Multilevel")
    duration_minutes = Column(Integer, default=60)
    
    is_demo = Column(Boolean, default=False)
    is_free = Column(Boolean, default=False)
    is_mock = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Bog'lanishlar
    tasks = relationship("WritingTask", back_populates="exam", cascade="all, delete-orphan", lazy="selectin")
    results = relationship("WritingResult", back_populates="exam", cascade="all, delete-orphan")
    
    # MockExam bilan teskari bog'lanish (Viewonly chunki FK MockExam'da)
    mock_exams = relationship("MockExam", back_populates="writing_test")

# --- WRITING TASK (Savollar) ---
class WritingTask(Base):
    __tablename__ = "writing_tasks"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(String, ForeignKey("writing_exams.id", ondelete="CASCADE"), nullable=False)
    
    part_number = Column(Integer, nullable=False) # 1 yoki 2
    type = Column(Enum(WritingTaskType, native_enum=False), nullable=False)
    
    topic = Column(Text, nullable=False) # Savol matni
    instruction = Column(Text, nullable=False) # Yo'riqnoma
    context_text = Column(Text, nullable=True) # Vaziyat (Email kimdan kelgan)
    
    min_words = Column(Integer, default=50)
    max_words = Column(Integer, default=200)

    exam = relationship("WritingExam", back_populates="tasks")

# --- WRITING RESULT (Natijalar) ---
class WritingResult(Base):
    __tablename__ = "writing_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String, ForeignKey("writing_exams.id", ondelete="CASCADE"), nullable=False)
    
    # --- MUHIM: EXAMS MODULIDAGI ATTEMPT BILAN BOG'LASH ---
    exam_attempt_id = Column(
        Integer, 
        ForeignKey("mock_exam_attempts.id", ondelete="CASCADE"), 
        nullable=True
    )
    raw_score = Column(Float)

    user_responses = Column(JSON, nullable=False) # {"task1": "matn", "task2": "matn"}
    overall_score = Column(Float, default=0.0)
    ai_evaluation = Column(JSON, nullable=True) # AI feedbacklari
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    user = relationship("User", backref="writing_results")
    exam = relationship("WritingExam", back_populates="results")
    
    # Attempt bilan bog'liqlik (SkillAttempt o'rniga to'g'ridan-to'g'ri ulanish)
    attempt = relationship("MockExamAttempt", backref="writing_results")

