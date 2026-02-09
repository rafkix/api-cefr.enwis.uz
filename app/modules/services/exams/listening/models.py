import enum
from sqlalchemy import (
    JSON, Column, DateTime, Float, Integer, String, Text, Enum, ForeignKey, Boolean, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base

class ListeningQuestionType(str, enum.Enum):
    MULTIPLE_CHOICE = "MULTIPLE_CHOICE"
    GAP_FILL = "GAP_FILL"
    MATCHING = "MATCHING"
    MAP_DIAGRAM = "MAP_DIAGRAM"
    SENTENCE_COMPLETION = "SENTENCE_COMPLETION"
    SHORT_ANSWER = "SHORT_ANSWER"

class ListeningExam(Base):
    __tablename__ = "listening_exams"

    id = Column(String, primary_key=True, index=True)
    title = Column(String, nullable=False)
    
    is_demo = Column(Boolean, default=False)
    is_free = Column(Boolean, default=False)
    is_mock = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    
    cefr_level = Column(String, default="B2")
    duration_minutes = Column(Integer, default=35)
    total_questions = Column(Integer, default=35)
    sections = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    parts = relationship(
        "ListeningPart", 
        back_populates="exam", 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )
    results = relationship(
        "ListeningResult", 
        back_populates="exam", 
        cascade="all, delete-orphan"
    )

class ListeningPart(Base):
    __tablename__ = "listening_parts"

    id = Column(Integer, primary_key=True, index=True)
    exam_id = Column(String, ForeignKey("listening_exams.id", ondelete="CASCADE"), nullable=False)
    
    part_number = Column(Integer, nullable=False)
    title = Column(String, nullable=False)
    instruction = Column(Text, nullable=False)
    task_type = Column(String, nullable=False)
    
    audio_url = Column(String, nullable=False)
    context = Column(String, nullable=True)
    passage = Column(Text, nullable=True)
    map_image = Column(String, nullable=True)

    exam = relationship("ListeningExam", back_populates="parts")
    
    questions = relationship(
        "ListeningQuestion", 
        back_populates="part", 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )
    
    options = relationship(
        "ListeningPartOption", 
        back_populates="part", 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )

class ListeningQuestion(Base):
    __tablename__ = "listening_questions"

    id = Column(Integer, primary_key=True, index=True)
    part_id = Column(Integer, ForeignKey("listening_parts.id", ondelete="CASCADE"), nullable=False)
    
    question_number = Column(Integer, nullable=False)
    type = Column(Enum(ListeningQuestionType, native_enum=False), nullable=False)
    
    text = Column(Text, nullable=True)
    correct_answer = Column(String, nullable=False)

    part = relationship("ListeningPart", back_populates="questions")
    
    options = relationship(
        "ListeningQuestionOption", 
        back_populates="question", 
        cascade="all, delete-orphan", 
        lazy="selectin"
    )

class ListeningPartOption(Base):
    __tablename__ = "listening_part_options"
    
    id = Column(Integer, primary_key=True, index=True)
    part_id = Column(Integer, ForeignKey("listening_parts.id", ondelete="CASCADE"), nullable=False)
    
    value = Column(String, nullable=False)
    label = Column(String, nullable=False)

    part = relationship("ListeningPart", back_populates="options")

class ListeningQuestionOption(Base):
    __tablename__ = "listening_question_options"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("listening_questions.id", ondelete="CASCADE"), nullable=False)
    
    value = Column(String, nullable=False)
    label = Column(String, nullable=False)

    question = relationship("ListeningQuestion", back_populates="options")

class ListeningResult(Base):
    __tablename__ = "listening_results"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    exam_id = Column(String, ForeignKey("listening_exams.id", ondelete="CASCADE"), nullable=False)
    
    exam_attempt_id = Column(
        Integer, 
        ForeignKey("mock_exam_attempts.id", ondelete="CASCADE"), 
        nullable=True
    )
    
    raw_score = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    correct_answers = Column(Integer, default=0)
    
    standard_score = Column(Float, default=0.0)
    cefr_level = Column(String, nullable=True)
    percentage = Column(Float, default=0.0)
    
    user_answers = Column(JSON, nullable=False, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    exam = relationship("ListeningExam", back_populates="results")