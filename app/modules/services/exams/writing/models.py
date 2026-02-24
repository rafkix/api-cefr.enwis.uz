import enum
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
    Index,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.modules.auth.models import User


# ==========================================================
# ENUMS
# ==========================================================

class CEFRLevel(str, enum.Enum):
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"


class WritingStyle(str, enum.Enum):
    INFORMAL = "INFORMAL"
    FORMAL = "FORMAL"
    POST = "POST"


class ScoringMode(str, enum.Enum):
    HOLISTIC = "HOLISTIC"
    ANALYTIC = "ANALYTIC"


class WritingCriterion(str, enum.Enum):
    TASK_ACHIEVEMENT = "task_achievement"
    COHERENCE = "coherence"
    VOCABULARY = "vocabulary"
    GRAMMAR = "grammar"
    MECHANICS = "mechanics"
    OVERALL = "overall"


class FeedbackSource(str, enum.Enum):
    AI = "AI"
    HUMAN = "HUMAN"


# ==========================================================
# WRITING FORMAT
# ==========================================================

class WritingFormat(Base):
    __tablename__ = "writing_formats"

    id = Column(Integer, primary_key=True)

    name = Column(String(50), nullable=False, unique=True)
    cefr_level = Column(Enum(CEFRLevel, native_enum=False), nullable=False)

    min_words = Column(Integer, nullable=False)
    max_words = Column(Integer, nullable=False)

    style = Column(Enum(WritingStyle, native_enum=False), nullable=False)
    scoring_mode = Column(Enum(ScoringMode, native_enum=False), nullable=False)

    penalty_enabled = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    tasks = relationship(
        "WritingTask",
        back_populates="format",
        cascade="all, delete",
        passive_deletes=True,
        lazy="selectin",
    )

    criterion_configs = relationship(
        "WritingCriterionConfig",
        back_populates="format",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# ==========================================================
# WRITING CRITERION CONFIG (weight system)
# ==========================================================

class WritingCriterionConfig(Base):
    __tablename__ = "writing_criterion_configs"

    id = Column(Integer, primary_key=True)

    format_id = Column(
        Integer,
        ForeignKey("writing_formats.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    criterion = Column(
        Enum(WritingCriterion, native_enum=False),
        nullable=False,
    )

    weight = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("format_id", "criterion", name="uq_format_criterion"),
    )

    format = relationship("WritingFormat", back_populates="criterion_configs")


# ==========================================================
# WRITING EXAM
# ==========================================================

class WritingExam(Base):
    __tablename__ = "writing_exams"

    id = Column(String(30), primary_key=True)

    year = Column(Integer, nullable=False, index=True)
    sequence_number = Column(Integer, nullable=False)

    title = Column(String(255), nullable=False)
    cefr_level = Column(Enum(CEFRLevel, native_enum=False), nullable=False)

    duration_minutes = Column(
        Integer,
        nullable=False,
        default=60,
        server_default=text("60"),
    )

    is_demo = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_free = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_mock = Column(Boolean, nullable=False, default=False, server_default=text("0"))
    is_active = Column(Boolean, nullable=False, default=True, server_default=text("1"))

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("year", "sequence_number", name="uq_writing_year_sequence"),
        Index("ix_exam_year_sequence", "year", "sequence_number"),
    )

    tasks = relationship(
        "WritingTask",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    results = relationship(
        "WritingResult",
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# ==========================================================
# WRITING TASK
# ==========================================================

class WritingTask(Base):
    __tablename__ = "writing_tasks"

    id = Column(Integer, primary_key=True)

    exam_id = Column(
        String(30),
        ForeignKey("writing_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    format_id = Column(
        Integer,
        ForeignKey("writing_formats.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    part_number = Column(Integer, nullable=False)
    sub_part = Column(Integer)

    topic = Column(Text, nullable=False)
    instruction = Column(Text, nullable=False)
    context_text = Column(Text)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "exam_id",
            "part_number",
            "sub_part",
            name="uq_exam_part_structure",
        ),
    )

    exam = relationship("WritingExam", back_populates="tasks")
    format = relationship("WritingFormat", back_populates="tasks")

    answers = relationship(
        "WritingAnswer",
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# ==========================================================
# WRITING RESULT
# ==========================================================

class WritingResult(Base):
    __tablename__ = "writing_results"

    id = Column(Integer, primary_key=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    exam_id = Column(
        String(30),
        ForeignKey("writing_exams.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    raw_score = Column(Float)
    scaled_score = Column(Float)
    cefr_level = Column(Enum(CEFRLevel, native_enum=False))

    is_finalized = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_result_user_exam", "user_id", "exam_id"),
    )

    exam = relationship("WritingExam", back_populates="results")
    user = relationship("User", lazy="selectin")  # ✅ qo‘sh

    answers = relationship(
        "WritingAnswer",
        back_populates="result",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# ==========================================================
# WRITING ANSWER
# ==========================================================

class WritingAnswer(Base):
    __tablename__ = "writing_answers"

    id = Column(Integer, primary_key=True)

    result_id = Column(
        Integer,
        ForeignKey("writing_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    task_id = Column(
        Integer,
        ForeignKey("writing_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    content = Column(Text, nullable=False)
    word_count = Column(Integer, nullable=False)

    penalty = Column(Float, nullable=False, default=0.0, server_default=text("0"))

    raw_score = Column(Float)
    scaled_score = Column(Float)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("result_id", "task_id", name="uq_answer_per_task"),
    )

    result = relationship("WritingResult", back_populates="answers")
    task = relationship("WritingTask", back_populates="answers")
    

    scores = relationship(
        "WritingScore",
        back_populates="answer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )

    feedbacks = relationship(
        "WritingFeedback",
        back_populates="answer",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


# ==========================================================
# WRITING SCORE
# ==========================================================

class WritingScore(Base):
    __tablename__ = "writing_scores"

    id = Column(Integer, primary_key=True)

    answer_id = Column(
        Integer,
        ForeignKey("writing_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    criterion = Column(
        Enum(WritingCriterion, native_enum=False),
        nullable=False,
    )

    score = Column(Float, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("answer_id", "criterion", name="uq_score_per_criterion"),
    )

    answer = relationship("WritingAnswer", back_populates="scores")


# ==========================================================
# WRITING FEEDBACK (AI / HUMAN EXTENSIBLE)
# ==========================================================

class WritingFeedback(Base):
    __tablename__ = "writing_feedbacks"

    id = Column(Integer, primary_key=True)

    answer_id = Column(
        Integer,
        ForeignKey("writing_answers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source = Column(
        Enum(FeedbackSource, native_enum=False),
        nullable=False,
    )

    model_name = Column(String(100))
    content = Column(Text, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    answer = relationship("WritingAnswer", back_populates="feedbacks")