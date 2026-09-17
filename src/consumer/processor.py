import logging
from typing import Any
from uuid import UUID

import httpx2
from sqlalchemy import Interval, literal_column, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.conf import settings
from src.db.models import UTC_NOW, PaymentModel
from src.types import Status, WebhookEvent

logger = logging.getLogger(__name__)

LEASE = literal_column("interval '1 minute'", Interval)


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
            json=WebhookEvent(payment_id=payment_id, status=status).model_dump(
                mode="json",
            ),
        )
    if response.is_error:
        raise ProcessingWebhookError(
            f"webhook failed with {response.status_code}: {response.text}"
        )


async def claim_payment(session: AsyncSession, payment_id: UUID) -> int | None:
    """Atomically take ownership of a pending payment."""
    async with session.begin():
        return (
            await session.execute(
                update(PaymentModel)
                .where(
                    PaymentModel.id == payment_id,
                    PaymentModel.status == "pending",
                    (
                        (PaymentModel.started_processing_at.is_(None))
                        | (PaymentModel.started_processing_at < UTC_NOW - LEASE)
                    ),
                )
                .values(
                    started_processing_at=UTC_NOW,
                    processing_attempts=PaymentModel.processing_attempts + 1,
                )
                .returning(PaymentModel.processing_attempts)
                .execution_options(synchronize_session=False)
            )
        ).scalar()


async def finish_payment(
    session: AsyncSession, payment_id: UUID, token: int, status: Status
) -> bool:
    """Write the final status. False means another consumer re-claimed the payment."""
    async with session.begin():
        update_id = (
            await session.execute(
                update(PaymentModel)
                .where(
                    PaymentModel.id == payment_id,
                    PaymentModel.processing_attempts == token,  # fencing
                )
                .values(status=status)
                .returning(PaymentModel.id)
                .execution_options(synchronize_session=False)
            )
        ).scalar()
    return update_id is not None


async def deliver_webhook(session: AsyncSession, payment_id: UUID) -> None:
    """Push the final status to the webhook at most once per payment."""
    async with session.begin():
        payment = (
            await session.execute(
                select(
                    PaymentModel.status,
                    PaymentModel.webhook_url,
                    PaymentModel.webhook_sent_at,
                ).where(PaymentModel.id == payment_id)
            )
        ).one_or_none()

    if payment is None:
        raise ProcessingNotFoundPaymentError

    if payment.status == "pendings":
        logger.warning(
            "payment %s is owned by another consumer, it will send the webhook",
            payment_id,
        )
        return

    if payment.webhook_sent_at is not None:
        logger.info("webhook for payment %s was already sent, skipping", payment_id)
        return

    await call_webhook(payment.webhook_url, payment_id, payment.status)

    async with session.begin():
        await session.execute(
            update(PaymentModel)
            .where(
                PaymentModel.id == payment_id,
                PaymentModel.webhook_sent_at.is_(None),
            )
            .values(webhook_sent_at=UTC_NOW)
            .execution_options(synchronize_session=False)
        )


async def process_new_payment(session: AsyncSession, payment_id: UUID) -> None:
    token = await claim_payment(session, payment_id)

    if token is not None:
        logger.info("emulating payment processing for payment %s", payment_id)
        try:
            await emulate_payment_processing(
                idempotency_key=payment_id,
                # here would be more arguments but we are emulating
            )
            status = "succeeded"
            logger.info("succeeded emulation for payment %s", payment_id)
        except EmulatingProcessingError:
            status = "failed"
            logger.info("failed emulation for payment %s", payment_id)

        if not await finish_payment(session, payment_id, token, status):
            logger.warning("payment %s was re-claimed, skipping webhook", payment_id)
            return

    # run after processing and on a retry
    await deliver_webhook(session, payment_id)
