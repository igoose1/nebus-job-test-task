from faststream import FastStream
from faststream.rabbit import RabbitBroker

from src.conf import settings
from src.consumer.processor import process_new_payment


async def main() -> None:
    broker = RabbitBroker(str(settings.mq_url))
    broker.subscriber("payments.new")(process_new_payment)
    app = FastStream(broker)
    await app.run()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
