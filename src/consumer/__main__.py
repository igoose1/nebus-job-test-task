import asyncio
import contextlib
import logging
from collections.abc import AsyncGenerator

from faststream import ContextRepo, FastStream
from faststream.rabbit import Channel, RabbitBroker

from src.conf import settings
from src.consumer.handlers import router
from src.db.sessions import create_engine, create_session_factory
from src.mq import DLQ, RETRY_QUEUES

logger = logging.getLogger(__name__)

BROKER_PREFETCH_COUNT = 50


def create_app() -> FastStream:
    broker = RabbitBroker(
        str(settings.mq_url),
        default_channel=Channel(
            publisher_confirms=True,
            on_return_raises=True,
            prefetch_count=BROKER_PREFETCH_COUNT,
        ),
    )
    broker.include_router(router)

    @contextlib.asynccontextmanager
    async def lifespan(context: ContextRepo) -> AsyncGenerator[None]:
        engine = create_engine(str(settings.db_url))
        context.set_global("session_factory", create_session_factory(engine))

        await broker.connect()
        for queue in (*RETRY_QUEUES, DLQ):
            await broker.declare_queue(queue)

        try:
            yield
        finally:
            await engine.dispose()

    return FastStream(broker, lifespan=lifespan)


if __name__ == "__main__":
    asyncio.run(create_app().run())
