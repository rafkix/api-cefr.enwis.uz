import enum
from sqlalchemy import (
    Column, Integer, String, Text, Float,
    Boolean, DateTime, ForeignKey, Enum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

# Bog'liq modellarni import
from app.modules.services.exams.reading.models import ReadingTest
from app.modules.services.exams.listening.models import ListeningExam

# --- ENUMS ---
class SkillType(str, enum.Enum):
    READING = "READING"
    LISTENING = "LISTENING"
    WRITING = "WRITING"
    SPEAKING = "SPEAKING"

# --- MOCK EXAM ---
class MockExam(Base):
    __tablename__ = "mock_exams"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    image_file = Column(String, nullable=True)
    cefr_level = Column(String, default="Multilevel")
    duration_minutes = Column(Integer, default=180)
    price = Column(Float, default=0.0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Foreign keys
    reading_id = Column(String, ForeignKey("reading_tests.id"), nullable=True)
    listening_id = Column(String, ForeignKey("listening_exams.id"), nullable=True)
    writing_id = Column(String, nullable=True)
    speaking_id = Column(String, nullable=True)

    # Relationships
    reading_test = relationship("ReadingTest", viewonly=True, uselist=False)
    listening_test = relationship("ListeningExam", viewonly=True, uselist=False)
    attempts = relationship("MockExamAttempt", back_populates="exam", cascade="all, delete-orphan")

# --- EXAM ATTEMPT ---
class MockExamAttempt(Base):
    __tablename__ = "mock_exam_attempts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mock_exam_id = Column(String, ForeignKey("mock_exams.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    is_finished = Column(Boolean, default=False)

    exam = relationship("MockExam", back_populates="attempts")
    skills = relationship("MockSkillAttempt", back_populates="attempt", cascade="all, delete-orphan")
    result = relationship("MockExamResult", back_populates="attempt", uselist=False, cascade="all, delete-orphan")

# --- SKILL ATTEMPT ---
class MockSkillAttempt(Base):
    __tablename__ = "mock_skill_attempts"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attempt_id = Column(Integer, ForeignKey("mock_exam_attempts.id", ondelete="CASCADE"), nullable=False)
    skill = Column(Enum(SkillType, native_enum=False), nullable=False)
    
    raw_score = Column(Float, default=0.0)
    scaled_score = Column(Float, default=0.0)
    cefr_level = Column(String, nullable=True)
    user_answers = Column(JSON, nullable=True)
    is_checked = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True, default=None)

    attempt = relationship("MockExamAttempt", back_populates="skills")

# --- EXAM RESULT ---
class MockExamResult(Base):
    __tablename__ = "mock_exam_results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    attempt_id = Column(Integer, ForeignKey("mock_exam_attempts.id", ondelete="CASCADE"), unique=True, nullable=False)

    reading_ball = Column(Float, default=0.0)
    listening_ball = Column(Float, default=0.0)
    writing_ball = Column(Float, default=0.0)
    speaking_ball = Column(Float, default=0.0)

    overall_score = Column(Float, default=0.0)
    cefr_level = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    attempt = relationship("MockExamAttempt", back_populates="result")

# --- PURCHASE ---
class MockPurchase(Base):
    __tablename__ = "mock_purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    mock_exam_id = Column(String, ForeignKey("mock_exams.id", ondelete="CASCADE"), nullable=False)
    is_active = Column(Boolean, default=False)
    comment = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", backref="purchased_mocks")
    exam = relationship("MockExam")
