import contextlib
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import FastAPI

from src.api.endpoints import router
from src.conf import settings
from src.db.sessions import create_engine, create_session_factory


@contextlib.asynccontextmanager
async def lifespan(_: Any) -> AsyncGenerator[dict[str, Any]]:
    engine = create_engine(str(settings.db_url))
    session_factory = create_session_factory(engine)

    yield {
        "session_factory": session_factory,
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
