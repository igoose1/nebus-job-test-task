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
        stmt = select(PaymentModel).where(
            PaymentModel.id == payment_id,
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
    if not payment:
        raise ProcessingNotFoundPaymentError

    if payment.status == "pending":
        if not payment.started_processing_at:
            logger.info("emulating payment processing for payment %s", payment_id)
            try:
                await emulate_payment_processing(
                    idempotency_key=payment.id,
                    # here would be more arguments but we are emulating
                )
            except EmulatingProcessingError:
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
                            status="failed",
                            processing_attempts=payment.processing_attempts + 1,
                        ),
                    )
            logger.info("succeeded emulation for payment %s", payment_id)
        else:
            logger.warning(
                "attempted to process payment %s owned by another consumer, that consumer may be dead",
                payment_id,
            )
    else:
        logger.warning(
            "attempted to process non-pending payment %s, skipping",
            payment_id,
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
                status="succeeded",
                processing_attempts=payment.processing_attempts + 1,
            ),
        )

    # TODO: call a webhook
