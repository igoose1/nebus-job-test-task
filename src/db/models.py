import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base
from src.types import Currency, Status


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
    created_at: Mapped[datetime.datetime]
    processed_at: Mapped[datetime.datetime | None] = mapped_column(default=None)
