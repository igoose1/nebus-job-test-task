# Async payment processing

## Run

Copy `.env.example` into `.env`. You may want to change `SERVICE_LISTEN_HOST` and `SERVICE_LISTEN_PORT`.

Launch services with docker compose.

```sh
cp .env.example .env

docker compose up
```

## Test manually

You can test the project by opening http://127.0.0.1:1234/docs. Send a POST request to `/api/v1/payments` with a random idempotency key. Default API Key: `key`. Receive updates on your `webhook_url` (specified in a body) or through a GET request to `/api/v1/payments/{payment_id}`.

Or run curl:

```sh
$ curl -X 'POST' \
  'http://127.0.0.1:1234/api/v1/payments' \
  -H 'accept: */*' \
  -H 'idempotency-key: test' \
  -H 'x-api-key: key' \
  -H 'Content-Type: application/json' \
  -d '{
  "amount": 1,
  "currency": "RUB",
  "description": "string",
  "metadata": {
    "user_id": 123
  },
  "webhook_url": "http://webhook_server:12345"
}'
{"payment_id":"01a0b3ef-1e0e-7129-8c93-8d5335516f3f","status":"pending","created_at":"2026-09-18T09:53:07.600590Z"}

$ curl -H 'x-api-key: key' http://127.0.0.1:1234/api/v1/payments/01a0b3ef-1e0e-7129-8c93-8d5335516f3f
{"payment_id":"01a0b3ef-1e0e-7129-8c93-8d5335516f3f","status":"succeeded","amount":"1","currency":"RUB","description":"string","metadata":{"user_id":123},"webhook_url":"http://webhook_server:12345/","created_at":"2026-09-18T09:53:07.600590Z","processed_at":"2026-09-18T09:53:11.035717Z"}
```

If you run a new POST request with the same data (body and idempotency key), API returns the same `payment_id`. If body differs, you get a 409 HTTP error.

## Test with a script

This project includes two scripts to test server's throughput:

- `scripts/finicky_server.py` --- a web-server which receives any webhook and fails with a 50% rate,
- `scripts/pusher.py` --- a script which pushes as many RPS as possible to a given endpoint.

`finicky_server` is included in the docker compose and runs by the name "webhook_server".

To test automatically, run this:

```sh
uv run scripts/pusher.py http://127.0.0.1:1234/api/v1/payments 100 10 http://webhook_server:12345 key
```

This will attempt to send 100 RPS for 10 seconds. In reality, OS and Python limits don't guarantee that `pusher.py` sends exactly 100 requests for exactly 10 seconds but this is still a good way to measure if a server survives any highload.

If you run, you find similar output:

```sh
$ time uv run scripts/pusher.py http://127.0.0.1:1234/api/v1/payments 100 10 http://webhook_server:12345 key
sent 1000 requests
202: 1000
uv run scripts/pusher.py http://127.0.0.1:1234/api/v1/payments 100 10  key  1.53s user 0.22s system 17% cpu 10.241 total
```

...meaning 1000 requests received 1000 responses with status code 202.

webhook_server logs RPS to itself:

```plain
webhook_server-1  | 06:41:50     13 rps   200=10 500=3
webhook_server-1  | 06:41:51     31 rps   200=17 500=14
webhook_server-1  | 06:41:52     55 rps   200=24 500=31
webhook_server-1  | 06:41:53     95 rps   200=54 500=41
webhook_server-1  | 06:41:54    111 rps   200=55 500=56
webhook_server-1  | 06:41:55    132 rps   200=73 500=59
webhook_server-1  | 06:41:56    133 rps   200=69 500=64
webhook_server-1  | 06:41:57    156 rps   200=73 500=83
webhook_server-1  | 06:41:58    166 rps   200=78 500=88
webhook_server-1  | 06:41:59    158 rps   200=70 500=88
webhook_server-1  | 06:42:00    183 rps   200=81 500=102
webhook_server-1  | 06:42:01    163 rps   200=80 500=83
webhook_server-1  | 06:42:02    117 rps   200=51 500=66
webhook_server-1  | 06:42:03     87 rps   200=42 500=45
webhook_server-1  | 06:42:04     58 rps   200=26 500=32
webhook_server-1  | 06:42:05     48 rps   200=24 500=24
webhook_server-1  | 06:42:06     35 rps   200=21 500=14
webhook_server-1  | 06:42:07     18 rps   200=6 500=12
webhook_server-1  | 06:42:08     15 rps   200=10 500=5
webhook_server-1  | 06:42:09      5 rps   200=2 500=3
webhook_server-1  | 06:42:10      2 rps   200=1 500=1
```

...showing a probability distribution of an emulated payment processing delay. Note that webhook server fails (sends 500) with a 50% rate, this is deliberate. Our payment server never sent an internal error code.

## Performance

It's easy to scale this project: add PgBouncer, add more API servers, add more consumers, voilà, we can scale until we hit PostgreSQL's write thoughput, working set size, etc.

Even though API server is a simple uvicorn server making 1--2 `INSERT`s, I was curious to test how many RPS I can throw at this API. I used wrk and a custom script (see `scripts/wrk-payments.lua`) to send POST requests with a random idempotency key.

On Ryzen 7 8840HS, I got over 1.5K RPS with 4 workers:

```plain
$ wrk -t32 -c1000 -d10s --timeout 10s --latency -s scripts/wrk-payments.lua http://127.0.0.1:1234/api/v1/payments
Running 10s test @ http://127.0.0.1:1234/api/v1/payments
  32 threads and 1000 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency   605.98ms  488.76ms   4.34s    70.92%
    Req/Sec    57.32     36.41   200.00     60.85%
  Latency Distribution
     50%  449.02ms
     75%  932.96ms
     90%    1.23s
     99%    2.30s
  16906 requests in 10.10s, 3.99MB read
Requests/sec:   1673.91
Transfer/sec:    404.95KB

sent 16906 requests in 10.10s (1674 rps)
202: 16906
latency  p50 449.0ms  p95 1444.7ms  p99 2300.7ms  max 4342.0ms
```

## Architecture overview

Events are created by an API server and processed by consumers:

- Outbox pattern for `payments.new`,
- `relay` service publishes messages from `outbox_messages` to `payments.new`,
- `consumer` service reads `payments.new`, attempts to process the payment and send a webhook,
- failed processing pushes events to 2 retry queues for exponential backoffs (20s, 40s),
- events failed after 3 attempts go to `payments.dlq`,

Currently there's one consumer service. Code is written in a way that it's easy to create new consumers: rows get claimed with fencing tokens, lease is temporary (new worker can pick up a dead consumer's task).

Much attention was put into safety of retries. I assumed that a payment provider we emulate supports idempotency keys which makes retries safe. As an idempotency key for an emulated provider I used payment.id, not user's provided idempotency key.

## Payment processing emulation

Emulation is an awaitable callable object:

```python
async def emulate_payment_processing(**_data: Any) -> None:
    import asyncio
    import random

    # emulate delays
    await asyncio.sleep(random.random() * 3 + 2)

    # emulate errors at a 10% rate
    if random.random() < 0.1:
        raise EmulatingProcessingError("not today")
```

In this code, I process EmulatingProcessingError as a "failed" transaction. In real life, there would be different failures: server can decline the payment, network can fail, etc. Different types of errors requires different approach.

## Potential improvements

This isn't a production ready code. If I had more time, I'd:

- Add unit tests, add integration tests,
- Split "process payment" and "send webhook" into two different events with their own retries,
- Store webhook results,
- Track consumers' rate, errors, and duration to find anomalies before users,
- Track API and consumers' utilization and saturation to scale when necessary,
- Limit string lengths, metadata size,
- Add better security: custom API keys, protect from SSRF in webhook_url,
- Re-use HTTP client,
- Write a better Dockerfile (multi-stage, non-root user), better .dockerignore.

## AI usage

LLM coded `src/relay` and `scripts/` files. The rest of the code, documentation and git commits were written by me.
