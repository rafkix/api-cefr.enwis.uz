import enum
from sqlalchemy import (
    Column, Integer, String, Text, Float,
    Boolean, DateTime, ForeignKey, Enum, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class ReadingQuestionType(str, enum.Enum):
    GAP_FILL = "GAP_FILL"
    GAP_FILL_FILL = "GAP_FILL_FILL"
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    TRUE_FALSE_NOT_GIVEN = "TRUE_FALSE_NOT_GIVEN"
    HEADINGS_MATCH = "HEADINGS_MATCH"
    TEXT_MATCH = "TEXT_MATCH"
    MULTIPLE_SELECT = "MULTIPLE_SELECT"

class ReadingTest(Base):
    __tablename__ = "reading_tests"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    cefr_level = Column(String, nullable=False)
    language = Column(String, default="en")
    duration_minutes = Column(Integer, default=60)
    total_questions = Column(Integer, nullable=False)

    is_demo = Column(Boolean, default=False)
    is_free = Column(Boolean, default=False)
    is_mock = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parts = relationship(
        "ReadingPart",
        back_populates="test",
        cascade="all, delete-orphan"
    )

    results = relationship(
        "ReadingResult",
        back_populates="test",
        cascade="all, delete-orphan"
    )

class ReadingPart(Base):
    __tablename__ = "reading_parts"

    id = Column(Integer, primary_key=True)
    test_id = Column(String, ForeignKey("reading_tests.id", ondelete="CASCADE"), nullable=False)
    
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    passage = Column(Text, nullable=False)

    test = relationship("ReadingTest", back_populates="parts")

    questions = relationship(
        "ReadingQuestion",
        back_populates="part",
        cascade="all, delete-orphan"
    )

class ReadingQuestion(Base):
    __tablename__ = "reading_questions"

    id = Column(Integer, primary_key=True)
    part_id = Column(Integer, ForeignKey("reading_parts.id", ondelete="CASCADE"), nullable=False)
    
    question_number = Column(Integer, nullable=False)
    type = Column(Enum(ReadingQuestionType, native_enum=False), nullable=False)
    text = Column(Text, nullable=False)
    correct_answer = Column(JSON, nullable=False)
    word_limit = Column(Integer, default=0)

    part = relationship("ReadingPart", back_populates="questions")

    options = relationship(
        "ReadingOption",
        back_populates="question",
        cascade="all, delete-orphan"
    )

class ReadingOption(Base):
    __tablename__ = "reading_options"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("reading_questions.id", ondelete="CASCADE"), nullable=False)
    
    label = Column(String, nullable=False)
    value = Column(String, nullable=False)

    question = relationship("ReadingQuestion", back_populates="options")

class ReadingResult(Base):
    __tablename__ = "reading_results"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    test_id = Column(String, ForeignKey("reading_tests.id", ondelete="CASCADE"), nullable=False)
    
    exam_attempt_id = Column(
        Integer,
        ForeignKey("mock_exam_attempts.id", ondelete="CASCADE"),
        nullable=True
    )

    raw_score = Column(Integer, nullable=False)
    percentage = Column(Float, nullable=False)
    cefr_level = Column(String, nullable=False)
    user_answers = Column(JSON, nullable=False)
    standard_score = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    test = relationship("ReadingTest", back_populates="results")