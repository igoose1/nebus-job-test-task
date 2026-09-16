import contextlib
from collections.abc import AsyncIterator
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.api.endpoints import router
from src.conf import settings


@contextlib.asynccontextmanager
async def lifespan(_: Any) -> AsyncIterator[dict[str, Any]]:
    engine = create_async_engine(url=str(settings.db_url), echo=True)
    sessionmaker = async_sessionmaker(engine)

    yield {
        "engine": engine,
        "sessionmaker": sessionmaker,
    }

    await engine.dispose()


app = FastAPI(lifespan=lifespan)
app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    with contextlib.suppress(KeyboardInterrupt):
        server = uvicorn.Server(
            uvicorn.Config(
                app,
                host=settings.listen_host,
                port=settings.listen_port,
            )
        )
        server.run()
