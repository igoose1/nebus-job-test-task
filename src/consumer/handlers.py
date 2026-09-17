import logging
from collections.abc import AsyncIterator
from typing import Annotated

from faststream import AckPolicy, Context, Depends
from faststream.rabbit import RabbitRouter
from faststream.rabbit.annotations import RabbitBroker, RabbitMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.consumer.processor import process_new_payment
from src.mq import EXCHANGE, PAYMENTS, RETRY_QUEUES
from src.types import NewPaymentEvent

logger = logging.getLogger(__name__)

router = RabbitRouter()


async def get_session(
    session_factory: Annotated[async_sessionmaker[AsyncSession], Context()],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.subscriber(
    PAYMENTS,
    EXCHANGE,
    ack_policy=AckPolicy.NACK_ON_ERROR,
)
async def handle_new_payment(
    event: NewPaymentEvent,
    message: RabbitMessage,
    broker: RabbitBroker,
    session: SessionDep,
) -> None:
    attempt = int(message.headers.get("x-attempt", 1))
    logger.info("processing payment_id %s attempt %d", event.payment_id, attempt)
    try:
        await process_new_payment(session, event.payment_id)
    except Exception as exc:  # noqa: BLE001
        if attempt > len(RETRY_QUEUES):
            logger.error("attempt %d failed as last: %r", attempt, exc)
            await message.reject()
            return
        retry_queue = RETRY_QUEUES[attempt - 1]
        logger.warning(
            "attempt %d failed, retrying with %s: %r", attempt, retry_queue.name, exc
        )
        await broker.publish(
            message.body,
            routing_key=retry_queue.name,
            message_id=message.message_id,
            content_type=message.content_type,
            headers={"x-attempt": attempt + 1},
            persist=True,
            mandatory=True,
        )
        await message.ack()
        return
    await message.ack()
    logger.info("succeeded %s", event.payment_id)
