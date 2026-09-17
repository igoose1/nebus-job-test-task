import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.types import Currency, Status

UTC_NOW = text("timezone('utc', now())")


class PaymentModel(Base):
    __tablename__ = "payments"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    amount: Mapped[Decimal]
    currency: Mapped[Currency]
    description: Mapped[str]
    payment_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON)
    status: Mapped[Status]
    idempotency_key: Mapped[str] = mapped_column(unique=True)
    webhook_url: Mapped[str]
    created_at: Mapped[datetime.datetime] = mapped_column(
        init=False, server_default=UTC_NOW
    )
    processed_at: Mapped[datetime.datetime | None] = mapped_column(default=None)


class OutboxMessageModel(Base):
    __tablename__ = "outbox_messages"

    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    routing_key: Mapped[str]
    payload: Mapped[bytes]
    attempts: Mapped[int] = mapped_column(default=0)
    next_attempt_at: Mapped[datetime.datetime] = mapped_column(
        init=False, server_default=UTC_NOW
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        init=False, server_default=UTC_NOW
    )
