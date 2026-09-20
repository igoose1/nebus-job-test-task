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
uv run scripts/pusher.py http://127.0.0.1:1234/api/v1/payments 100 10  key  1.32s user 0.16s system 14% cpu 10.172 total
```

...meaning 1000 requests received 1000 responses with status code 202.

webhook_server logs RPS to itself:

```plain
webhook_server-1  | 08:59:54      2 rps   500=2
webhook_server-1  | 08:59:55     44 rps   200=14 500=30
webhook_server-1  | 08:59:56     57 rps   200=32 500=25
webhook_server-1  | 08:59:57    116 rps   200=62 500=54
webhook_server-1  | 08:59:58     94 rps   200=48 500=46
webhook_server-1  | 08:59:59    103 rps   200=51 500=52
webhook_server-1  | 09:00:00     89 rps   200=37 500=52
webhook_server-1  | 09:00:01     97 rps   200=44 500=53
webhook_server-1  | 09:00:02    106 rps   200=60 500=46
webhook_server-1  | 09:00:03    106 rps   200=48 500=58
webhook_server-1  | 09:00:04     95 rps   200=48 500=47
webhook_server-1  | 09:00:05     66 rps   200=33 500=33
webhook_server-1  | 09:00:06     24 rps   200=13 500=11
webhook_server-1  | 09:00:07      1 rps   500=1
webhook_server-1  | 09:00:14      1 rps   200=1
webhook_server-1  | 09:00:15     30 rps   200=12 500=18
webhook_server-1  | 09:00:16     26 rps   200=14 500=12
webhook_server-1  | 09:00:17     54 rps   200=28 500=26
...
```

...showing a probability distribution of an emulated payment processing delay. Note that webhook server fails (sends 500) with a 50% rate, this is deliberate. Our payment server never sent an internal error code.

## Performance

It's easy to scale this project: add PgBouncer, add more API servers, add more consumers, voilà, we can scale until we hit PostgreSQL's write thoughput, working set size, etc.

Even though API server is a simple uvicorn server making 1--2 `INSERT`s, I was curious to test how many RPS I can throw at this API. I used wrk and a custom script (see `scripts/wrk-payments.lua`) to send POST requests with a random idempotency key.

On Ryzen 7 8840HS, I got almost 2K RPS with 4 workers:

```plain
$ wrk -t32 -c1000 -d10s --timeout 10s --latency -s scripts/wrk-payments.lua http://127.0.0.1:1234/api/v1/payments
Running 10s test @ http://127.0.0.1:1234/api/v1/payments
  32 threads and 1000 connections
  Thread Stats   Avg      Stdev     Max   +/- Stdev
    Latency   509.60ms  332.85ms   2.97s    73.13%
    Req/Sec    62.94     33.60   212.00     70.59%
  Latency Distribution
     50%  464.01ms
     75%  740.41ms
     90%  859.91ms
     99%    1.53s
  19431 requests in 10.10s, 4.59MB read
  Socket errors: connect 3, read 0, write 0, timeout 0
Requests/sec:   1923.86
Transfer/sec:    465.42KB

sent 19431 requests in 10.10s (1924 rps)
202: 19431
connect errors: 3
latency  p50 464.0ms  p95 1074.0ms  p99 1535.0ms  max 2971.0ms
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
