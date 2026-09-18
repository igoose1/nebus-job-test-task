from decimal import Decimal
from typing import Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel, Field

type Amount = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=2)]
type Currency = Literal["RUB", "USD", "EUR"]
type Status = Literal["pending", "succeeded", "failed"]


class NewPaymentEvent(BaseModel):
    payment_id: UUID


class WebhookEvent(BaseModel):
    event_type: ClassVar[Literal["payments.processed"]] = "payments.processed"
    payment_id: UUID
    status: Status
