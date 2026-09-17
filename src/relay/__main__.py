import asyncio
import logging

from faststream.rabbit import Channel, ExchangeType, RabbitBroker, RabbitExchange
from sqlalchemy import (
    DateTime,
    Interval,
    delete,
    func,
    literal_column,
    select,
    tuple_,
    update,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from src.conf import settings
from src.db.models import OutboxMessageModel
from src.db.sessions import create_engine

logger = logging.getLogger("relay")

EXCHANGE = RabbitExchange("events", type=ExchangeType.TOPIC, durable=True)
BATCH_SIZE = settings.relay_batch_size
POLL_INTERVAL = settings.relay_poll_interval.total_seconds()
PUBLISH_TIMEOUT = settings.relay_publish_timeout.total_seconds()

UTC_NOW = literal_column("timezone('utc', now())", DateTime)
SECOND = literal_column("interval '1 second'", Interval)
LEASE = 60 * SECOND
BACKOFF = (
    func.least(func.power(2, func.least(OutboxMessageModel.publish_attempts, 16)), 60)
    * SECOND
)

CLAIM = (
    update(OutboxMessageModel)
    .where(
        OutboxMessageModel.id.in_(
            select(OutboxMessageModel.id)
            .where(OutboxMessageModel.next_attempt_at <= UTC_NOW)
            .order_by(OutboxMessageModel.id)
            .limit(BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
    )
    .values(
        publish_attempts=OutboxMessageModel.publish_attempts + 1,
        next_attempt_at=UTC_NOW + LEASE,
    )
    .returning(
        OutboxMessageModel.id,
        OutboxMessageModel.routing_key,
        OutboxMessageModel.payload,
        OutboxMessageModel.publish_attempts,
    )
)


async def run_broker(broker: RabbitBroker, engine: AsyncEngine) -> None:
    async with broker:
        await broker.declare_exchange(EXCHANGE)
        logger.info("relay started")

        while True:
            async with engine.begin() as conn:
                rows = (await conn.execute(CLAIM)).all()

            results = await asyncio.gather(
                *(
                    broker.publish(
                        row.payload,
                        exchange=EXCHANGE,
                        routing_key=row.routing_key,
                        message_id=str(row.id),
                        content_type="application/json",
                        headers={"x-attempt": 1},
                        persist=True,
                        mandatory=True,
                        timeout=PUBLISH_TIMEOUT,
                    )
                    for row in rows
                ),
                return_exceptions=True,
            )

            published, failed = [], []
            for row, result in zip(rows, results, strict=True):
                if isinstance(result, Exception):
                    logger.warning(
                        "Failed to publish outbox message %s (publish attempt %d): %r",
                        row.id,
                        row.publish_attempts,
                        result,
                    )
                    failed.append((row.id, row.publish_attempts))
                else:
                    published.append((row.id, row.publish_attempts))

            # (id, publish_attempts) as a fencing token
            if published or failed:
                async with engine.begin() as conn:
                    if published:
                        await conn.execute(
                            delete(OutboxMessageModel).where(
                                tuple_(
                                    OutboxMessageModel.id,
                                    OutboxMessageModel.publish_attempts,
                                ).in_(published)
                            )
                        )
                    if failed:
                        await conn.execute(
                            update(OutboxMessageModel)
                            .where(
                                tuple_(
                                    OutboxMessageModel.id,
                                    OutboxMessageModel.publish_attempts,
                                ).in_(failed)
                            )
                            .values(next_attempt_at=UTC_NOW + BACKOFF)
                        )

            if len(rows) < BATCH_SIZE:
                await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    engine = create_engine(str(settings.db_url))
    broker = RabbitBroker(
        str(settings.mq_url),
        default_channel=Channel(publisher_confirms=True, on_return_raises=True),
    )

    try:
        await run_broker(broker, engine)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
