# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn", "typer"]
# ///

import asyncio
import random
import sys
import time
from collections import Counter, defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any, Literal

import typer
import uvicorn
from fastapi import Body, FastAPI, HTTPException, status

INTERVAL = 1.0

buckets: defaultdict[int, Counter] = defaultdict(Counter)


def publish(second: int, counts: Counter) -> None:
    stamp = time.strftime("%H:%M:%S", time.localtime(second))
    detail = " ".join(f"{code}={n}" for code, n in sorted(counts.items()))
    print(
        f"{stamp} {sum(counts.values()):>6} rps   {detail}", file=sys.stderr, flush=True
    )


async def report() -> None:
    while True:
        await asyncio.sleep(INTERVAL)
        now = int(time.time())
        for second in sorted(s for s in buckets if s < now):
            publish(second, buckets.pop(second))


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    task = asyncio.create_task(report())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


app = FastAPI(lifespan=lifespan)


@app.post("/")
async def receive(payload: Any = Body(None)) -> Literal["OK"]:  # noqa: B008
    second = int(time.time())
    if random.random() < 0.5:
        buckets[second][status.HTTP_500_INTERNAL_SERVER_ERROR] += 1
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
    buckets[second][status.HTTP_200_OK] += 1
    return "OK"


def main(host: str, port: int) -> None:
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    typer.run(main)
