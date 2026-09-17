# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx2", "typer"]
# ///

import asyncio
import uuid
from collections import Counter
from collections.abc import Awaitable
from typing import Any

import httpx2
import typer

TIMEOUT = 10.0


async def send_one(
    client: httpx2.AsyncClient,
    url: str,
    results: Counter[Any],
    payload: dict[str, Any],
    api_key: str,
) -> None:
    headers = {"Idempotency-Key": str(uuid.uuid4()), "X-API-Key": api_key}
    try:
        resp = await client.post(url, json=payload, headers=headers)
        results[resp.status_code] += 1
    except httpx2.HTTPError as exc:
        results[type(exc).__name__] += 1


async def fire_at(
    loop: asyncio.AbstractEventLoop, when: float, coro: Awaitable[Any]
) -> None:
    delay = when - loop.time()
    if delay > 0:
        await asyncio.sleep(delay)
    await coro


async def run(
    url: str, rps: int, seconds: float, webhook_url: str, api_key: str
) -> Counter[Any]:
    payload = {
        "amount": 0,
        "currency": "RUB",
        "description": "nothing to see here",
        "metadata": {"user_id": 123},
        "webhook_url": webhook_url,
    }
    results: Counter[Any] = Counter()
    total = round(rps * seconds)
    async with httpx2.AsyncClient(timeout=TIMEOUT) as client:
        loop = asyncio.get_running_loop()
        start = loop.time()
        tasks = [
            asyncio.create_task(
                fire_at(
                    loop,
                    start + k / rps,
                    send_one(client, url, results, payload, api_key),
                )
            )
            for k in range(total)
        ]
        await asyncio.gather(*tasks)
    return results


def main(url: str, n: int, seconds: float, webhook_url: str, api_key: str) -> None:
    """Send N requests/second to URL for SECONDS with a specified WEBHOOK_URL in its body."""
    results = asyncio.run(run(url, n, seconds, webhook_url, api_key))
    print(f"sent {sum(results.values())} requests")
    for key, count in sorted(results.items(), key=lambda kv: str(kv[0])):
        print(f"{key}: {count}")


if __name__ == "__main__":
    typer.run(main)
