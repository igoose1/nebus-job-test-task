import logging
from typing import Any
from uuid import UUID

import httpx2
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.conf import settings
from src.db.models import UTC_NOW, PaymentModel
from src.types import Status, WebhookEvent

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


class ProcessingWebhookError(ProcessingError):
    """Raised when there's an issue with pushing to a webhook."""


async def call_webhook(webhook_url: str, payment_id: UUID, status: Status) -> None:
    async with httpx2.AsyncClient(
        timeout=settings.webhook_timeout.total_seconds(),
    ) as http:
        response = await http.post(
            webhook_url,
            data=WebhookEvent(payment_id=payment_id, status=status).model_dump(
                mode="json",
            ),
        )
    if response.is_error:
        raise ProcessingWebhookError(
            f"webhook failed with {response.status_code}: {response.text}"
        )


async def process_new_payment(session: AsyncSession, payment_id: UUID) -> None:
    async with session.begin():
        stmt = select(PaymentModel).where(
            PaymentModel.id == payment_id,
        )
        payment = (await session.execute(stmt)).scalar_one_or_none()
    if not payment:
        raise ProcessingNotFoundPaymentError

    new_status = None
    if payment.status == "pending":
        if not payment.started_processing_at:
            async with session.begin():
                await session.execute(
                    update(PaymentModel)
                    .where(
                        PaymentModel.id == payment_id,
                        PaymentModel.processing_attempts
                        == payment.processing_attempts,  # fencing
                    )
                    .values(
                        started_processing_at=UTC_NOW,
                    ),
                )
            logger.info("emulating payment processing for payment %s", payment_id)
            try:
                await emulate_payment_processing(
                    idempotency_key=payment.id,
                    # here would be more arguments but we are emulating
                )
                new_status = "succeeded"
                logger.info("succeeded emulation for payment %s", payment_id)
            except EmulatingProcessingError:
                logger.info("failed emulation for payment %s", payment_id)
                new_status = "failed"

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

    if new_status is None:
        return

    async with session.begin():
        await session.execute(
            update(PaymentModel)
            .where(
                PaymentModel.id == payment_id,
                PaymentModel.processing_attempts
                == payment.processing_attempts,  # fencing
            )
            .values(
                status=new_status,
                processing_attempts=payment.processing_attempts + 1,
            ),
        )
    await call_webhook(payment.webhook_url, payment_id, new_status)
