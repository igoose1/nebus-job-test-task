import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import PaymentModel

logger = logging.getLogger(__name__)


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
            logger.warning(
                "attempted to process payment %s concurrently, skipping", payment_id
            )
            return
        if payment.processing_status == "succeeded":
            logger.warning(
                "attempted to process succeeded payment %s, skipping", payment_id
            )
            return

    try:
        logger.info("emulating payment processing for payment %s", payment_id)
        await emulate_payment_processing(
            idempotency_key=payment.id,
            # here would be more arguments but we are emulating
        )
        logger.info("succeeded emulation for payment %s", payment_id)
        # if we are here, we succeeded
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
                    status="succeeded",
                    processing_attempts=payment.processing_attempts + 1,
                ),
            )
    except Exception:
        logger.info("failed emulation for payment %s", payment_id)
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
                    status="failed",
                    processing_attempts=payment.processing_attempts + 1,
                ),
            )
        raise

    # TODO: call a webhook
