from typing import ClassVar, Literal
from uuid import UUID

from pydantic import BaseModel

type Currency = Literal["RUB", "USD", "EUR"]
type Status = Literal["pending", "succeeded", "failed"]


class NewPaymentEvent(BaseModel):
    payment_id: UUID


class WebhookEvent(BaseModel):
    event_type: ClassVar[Literal["payments.processed"]] = "payments.processed"
    payment_id: UUID
    status: Status
