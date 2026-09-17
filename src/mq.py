from typing import Any

from faststream.rabbit import ExchangeType, QueueType, RabbitExchange, RabbitQueue

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
        f"payments.retry.{attempt}",
        arguments={
            "x-message-ttl": ttl_ms,
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": PAYMENTS.name,
            "x-dead-letter-strategy": "at-least-once",
            "x-overflow": "reject-publish",
        },
    )
    for attempt, ttl_ms in ((1, 10_000), (2, 40_000))
]

DLQ = quorum_queue("payments.dlq")
