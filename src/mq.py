from typing import Any

from faststream.rabbit import ExchangeType, QueueType, RabbitExchange, RabbitQueue

from src.conf import settings

EXCHANGE = RabbitExchange("events", type=ExchangeType.TOPIC, durable=True)


def quorum_queue(
    name: str,
    routing_key: str = "",
    arguments: Any | None = None,
) -> RabbitQueue:
    return RabbitQueue(
        name,
        durable=True,
        queue_type=QueueType.QUORUM,
        routing_key=routing_key,
        arguments=arguments,
    )


PAYMENTS = quorum_queue(
    "payments",
    routing_key="payments.new",
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "payments.dlq",
        "x-dead-letter-strategy": "at-least-once",
        "x-overflow": "reject-publish",
        "x-delivery-limit": 5,
    },
)

RETRY_QUEUES = [
    quorum_queue(
        f"payments.retry.{retry_attempt}",
        arguments={
            "x-message-ttl": 2**retry_attempt * 10_000,  # exponential backoff (in ms)
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": PAYMENTS.name,
            "x-dead-letter-strategy": "at-least-once",
            "x-overflow": "reject-publish",
        },
    )
    for retry_attempt in range(1, settings.max_attempts)
]

DLQ = quorum_queue("payments.dlq")
