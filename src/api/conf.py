from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    listen_host: str
    listen_port: int

    model_config = SettingsConfigDict(
        env_prefix="service_",
    )


settings = Settings()  # type: ignore
