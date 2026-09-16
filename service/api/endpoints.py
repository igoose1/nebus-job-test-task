from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import AwareDatetime, BaseModel, HttpUrl

router = APIRouter()


class CreatePaymentSchema(BaseModel):
    amount: Decimal
    currency: Literal["RUB", "USD", "EUR"]
    description: str
    metadata: dict[str, Any]
    webhook_url: HttpUrl


class ShortPaymentSchema(BaseModel):
    payment_id: UUID
    status: Literal["pending", "succeeded", "failed"]
    created_at: AwareDatetime


class DetailedPaymentSchema(BaseModel):
    payment_id: UUID
    status: Literal["pending", "succeeded", "failed"]
    amount: Decimal
    currency: Literal["RUB", "USD", "EUR"]
    description: str
    metadata: dict[str, Any]
    webhook_url: HttpUrl
    created_at: AwareDatetime
    processed_at: AwareDatetime


@router.post("/payments")
async def create_payment(
    body: CreatePaymentSchema,
    idempotency_key: Annotated[str, Header()],
) -> ShortPaymentSchema: ...


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: UUID,
) -> DetailedPaymentSchema: ...
