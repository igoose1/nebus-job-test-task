from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import PaymentModel


class ProcessingError(Exception):
    """Raised by processing units."""


class EmulatingProcessingError(ProcessingError):
    """Raised by an emulator."""


async def emulate_payment_processing(**_data: Any) -> None:
    import asyncio
    import random

    # emulate delays
    await asyncio.sleep(random.random() * 5)

    # emulate errors at a 10% rate
    if random.random() < 0.1:
        raise EmulatingProcessingError("not today")


class ProcessingNotFoundPaymentError(ProcessingError):
    """Raised when there's no payment by a specified ID."""


class ProcessingStartedPaymentError(ProcessingError):
    """Raised when a payment already started processing. DO NOT RETRY."""


async def process_new_payment(session: AsyncSession, payment_id: UUID) -> None:
    async with session.begin():
        stmt = (
            select(PaymentModel)
            .where(
                PaymentModel.id == payment_id,
            )
            .with_for_update()
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
        if not payment:
            raise ProcessingNotFoundPaymentError
        if payment.processing_status == "started":
            raise ProcessingStartedPaymentError

    try:
        if payment.processing_status in ("awaiting", "failed"):
            await emulate_payment_processing(
                idempotency_key=payment.id,
                # here would be more arguments but we are emulating
            )
            async with session.begin():
                await session.execute(
                    update(PaymentModel)
                    .where(
                        PaymentModel.id == payment_id,
                        PaymentModel.processing_attempts
                        == payment.processing_attempts,  # fencing
                    )
                    .values(
                        processing_status="succeeded",
                        processing_attempts=payment.processing_attempts + 1,
                    ),
                )
    except Exception:
        async with session.begin():
            await session.execute(
                update(PaymentModel)
                .where(
                    PaymentModel.id == payment_id,
                    PaymentModel.processing_attempts
                    == payment.processing_attempts,  # fencing
                )
                .values(
                    processing_status="failed",
                    processing_attempts=payment.processing_attempts + 1,
                ),
            )
        raise

    # TODO: call a webhook
