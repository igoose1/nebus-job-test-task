import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID, uuid7

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import AwareDatetime, BaseModel, HttpUrl
from sqlalchemy.exc import IntegrityError

from src.db.models import PaymentModel
from src.db.sessions import SessionDep
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
    processed_at: AwareDatetime | None


@router.post("/payments")
async def create_payment(
    body: CreatePaymentSchema,
    idempotency_key: Annotated[str, Header()],
    session: SessionDep,
) -> ShortPaymentSchema:
    payment = PaymentModel(
        id=uuid7(),
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        payment_metadata=body.metadata,
        status="pending",
        idempotency_key=idempotency_key,
        webhook_url=str(body.webhook_url),
        created_at=datetime.datetime.now(datetime.UTC),
    )
    async with session.begin():
        session.add(payment)
        try:
            await session.flush()
        except IntegrityError:
            # TODO: retrieve a cached payment
            ...
    return ShortPaymentSchema(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: UUID,
    session: SessionDep,
) -> DetailedPaymentSchema:
    async with session.begin():
        payment = await session.get(PaymentModel, payment_id)
    if not payment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "payment not found")
    return DetailedPaymentSchema(
        payment_id=payment.id,
        status=payment.status,
        amount=payment.amount,
        currency=payment.currency,
        description=payment.description,
        metadata=payment.payment_metadata,
        webhook_url=HttpUrl(payment.webhook_url),
        created_at=payment.created_at,
        processed_at=payment.processed_at,
    )
