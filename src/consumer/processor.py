import logging
from uuid import UUID

logger = logging.getLogger(__name__)


async def process_new_payment(payment_id: UUID) -> None:
    logger.info("processing payment_id=%s", payment_id)
    # TODO
