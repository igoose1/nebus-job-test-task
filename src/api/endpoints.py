from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Header
from pydantic import AwareDatetime, BaseModel, HttpUrl

from src.types import Currency, Status

router = APIRouter()


@router.get("/health")
async def healthcheck() -> Literal["OK"]:
    return "OK"


class CreatePaymentSchema(BaseModel):
    amount: Decimal
    currency: Currency
    description: str
    metadata: dict[str, Any]
    webhook_url: HttpUrl


class ShortPaymentSchema(BaseModel):
    payment_id: UUID
    status: Status
    created_at: AwareDatetime


class DetailedPaymentSchema(BaseModel):
    payment_id: UUID
    status: Status
    amount: Decimal
    currency: Currency
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
