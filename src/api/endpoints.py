import secrets
from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID, uuid7

from fastapi import APIRouter, Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from pydantic import AwareDatetime, BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.conf import settings
from src.db.models import OutboxMessageModel, PaymentModel
from src.db.sessions import SessionDep
from src.types import Currency, NewPaymentEvent, Status

router = APIRouter()


@router.get("/health")
async def healthcheck() -> Literal["OK"]:
    return "OK"


api_key_header = APIKeyHeader(name="x-api-key")


def validate_api_key(api_key_header: Annotated[str, Security(api_key_header)]) -> None:
    if secrets.compare_digest(settings.api_key, api_key_header):
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid API key")


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


def match_model_fields(model: PaymentModel, schema: CreatePaymentSchema) -> bool:
    return (
        model.amount == schema.amount
        and model.currency == schema.currency
        and model.description == schema.description
        and model.payment_metadata == schema.metadata
        and model.webhook_url == str(schema.webhook_url)
    )


@router.post("/payments")
async def create_payment(
    body: CreatePaymentSchema,
    idempotency_key: Annotated[str, Header()],
    session: SessionDep,
    _: Annotated[None, Security(validate_api_key)],
) -> ShortPaymentSchema:
    new = PaymentModel(
        id=uuid7(),
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        payment_metadata=body.metadata,
        status="pending",
        idempotency_key=idempotency_key,
        webhook_url=str(body.webhook_url),
    )
    message = OutboxMessageModel(
        routing_key="payments.new",
        payload=NewPaymentEvent(payment_id=new.id).model_dump_json().encode(),
    )

    try:
        async with session.begin():
            session.add_all([new, message])
        return ShortPaymentSchema(
            payment_id=new.id,
            status=new.status,
            created_at=new.created_at,
        )
    except IntegrityError:
        async with session.begin():
            previous = (
                await session.execute(
                    select(PaymentModel).where(
                        PaymentModel.idempotency_key == idempotency_key
                    )
                )
            ).scalar_one()
    if not match_model_fields(previous, body):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "idempotency key was repeated with a different payment data, use unique idempotency keys",
        )
    return ShortPaymentSchema(
        payment_id=previous.id,
        status=previous.status,
        created_at=previous.created_at,
    )


@router.get("/payments/{payment_id}")
async def get_payment(
    payment_id: UUID,
    session: SessionDep,
    _: Annotated[None, Security(validate_api_key)],
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
