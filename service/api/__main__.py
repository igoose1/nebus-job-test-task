import contextlib

from fastapi import FastAPI

from service.api.conf import settings
from service.api.endpoints import router

app = FastAPI()
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
