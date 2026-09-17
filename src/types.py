from typing import Literal
from uuid import UUID

from pydantic import BaseModel

type Currency = Literal["RUB", "USD", "EUR"]
type Status = Literal["pending", "succeeded", "failed"]


class NewPaymentEvent(BaseModel):
    payment_id: UUID
