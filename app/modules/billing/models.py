# app/modules/billing/models.py

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.modules.auth.models import User
from sqlalchemy.sql import func


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class SubscriptionPlan(Base, TimestampMixin):
    __tablename__ = "subscription_plans"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )

    price: Mapped[int] = mapped_column(Integer)
    duration_days: Mapped[int] = mapped_column(Integer)

    ai_limit: Mapped[int] = mapped_column(Integer)
    exam_limit: Mapped[int] = mapped_column(Integer)


class UserSubscription(Base, TimestampMixin):
    __tablename__ = "user_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("subscription_plans.id")
    )

    start_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
    )

    end_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    user: Mapped["User"] = relationship("User")
    plan: Mapped["SubscriptionPlan"] = relationship("SubscriptionPlan")


class BalanceTransaction(Base, TimestampMixin):
    __tablename__ = "balance_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )

    amount: Mapped[int] = mapped_column(Integer)  # + yoki -
    reason: Mapped[str] = mapped_column(String(100))

    reference_id: Mapped[Optional[str]] = mapped_column(String)

    user: Mapped["User"] = relationship("User")

class VerificationCode(Base, TimestampMixin):
    __tablename__ = "verification_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    target: Mapped[str] = mapped_column(String(255), index=True)
    code_hash: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        Index("idx_active_code", "target", "is_used"),
    )
