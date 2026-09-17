import logging

from faststream import AckPolicy, FastStream
from faststream.rabbit import RabbitBroker
from faststream.rabbit.annotations import RabbitMessage

from src.conf import settings
from src.consumer.processor import process_new_payment
from src.db.sessions import create_engine, create_session_factory
from src.mq import DLQ, EXCHANGE, PAYMENTS, RETRY_QUEUES
from src.types import NewPaymentEvent

logger = logging.getLogger(__name__)

broker = RabbitBroker(str(settings.mq_url))
broker.subscriber("payments.new")(process_new_payment)
app = FastStream(broker)
session_factory = create_session_factory(create_engine(str(settings.db_url)))


@broker.subscriber(
    PAYMENTS,
    EXCHANGE,
    ack_policy=AckPolicy.NACK_ON_ERROR,
)
async def handle_new_payment(event: NewPaymentEvent, message: RabbitMessage) -> None:
    attempt = int(message.headers.get("x-attempt", 1))
    logger.info("processing payment_id %s attempt %d", event.payment_id, attempt)
    try:
        async with session_factory() as session, session.begin():
            await process_new_payment(session, event.payment_id)
    except Exception as exc:  # noqa: BLE001
        if attempt > len(RETRY_QUEUES):
            logger.error("attempt %d failed as last: %r", attempt, exc)
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


async def main() -> None:
    async with broker:
        for queue in (*RETRY_QUEUES, DLQ):
            await broker.declare_queue(queue)
        await broker.start()
        await asyncio.Event().wait()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
