import datetime

from pydantic import AmqpDsn, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_key: str

    listen_host: str
    listen_port: int
    db_url: PostgresDsn
    mq_url: AmqpDsn
    api_workers: int = 4

    relay_batch_size: int = 100
    relay_poll_interval: datetime.timedelta = datetime.timedelta(seconds=1)
    relay_publish_timeout: datetime.timedelta = datetime.timedelta(seconds=10)

    max_attempts: int = 3

    webhook_timeout: datetime.timedelta = datetime.timedelta(seconds=10)

    model_config = SettingsConfigDict(
        env_prefix="service_",
    )


settings = Settings()  # type: ignore
