# /// script
# requires-python = ">=3.11"
# dependencies = ["fastapi", "uvicorn", "typer"]
# ///

import random
from typing import Any, Literal

import typer
import uvicorn
from fastapi import Body, FastAPI, HTTPException, status

app = FastAPI()


@app.post("/")
async def receive(payload: Any = Body(None)) -> Literal["OK"]:  # noqa: B008
    if random.random() < 0.5:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR)
    return "OK"


def main(host: str, port: int) -> None:
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    typer.run(main)
