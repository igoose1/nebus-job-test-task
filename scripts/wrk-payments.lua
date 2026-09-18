-- wrk/wrk2 script mirroring pusher.py
--
--   wrk2 -t8 -c200 -d10s -R1000 --latency -s wrk-payments.lua http://127.0.0.1:1234/api/v1/payments
--   wrk  -t8 -c200 -d10s        --latency -s wrk-payments.lua http://127.0.0.1:1234/api/v1/payments

local WEBHOOK_URL = "http://webhook_server:12345"
local API_KEY = "key"

local threads = {}
local thread_id = 0

-- Runs in the main VM, once per thread, before the thread starts.
function setup(thread)
  thread_id = thread_id + 1
  thread:set("id", thread_id)
  table.insert(threads, thread)
end

-- Runs inside each thread's own Lua VM.
function init(args)
  -- Every thread has a separate VM, so an unseeded RNG would make all threads
  -- emit an identical key sequence. Duplicate Idempotency-Keys would then be
  -- deduplicated server-side and quietly destroy the test.
  math.randomseed(os.time() * 1000 + id * 7919)
  for _ = 1, 5 do math.random() end

  counts = {}

  wrk.method = "POST"
  wrk.body = string.format(
    '{"amount":"67.00","currency":"RUB","description":"nothing to see here",'
      .. '"metadata":{"user_id":123},"webhook_url":"%s"}',
    WEBHOOK_URL
  )
  wrk.headers["Content-Type"] = "application/json"
  wrk.headers["X-API-Key"] = API_KEY
end

-- UUIDv4 shape from eight 16-bit draws. Each value stays well inside integer
-- range, which %x formatting on LuaJIT needs.
local function idempotency_key()
  return string.format(
    "%04x%04x-%04x-4%03x-%04x-%04x%04x%04x",
    math.random(0, 0xffff), math.random(0, 0xffff),
    math.random(0, 0xffff),
    math.random(0, 0xfff),
    math.random(0x8000, 0xbfff),
    math.random(0, 0xffff), math.random(0, 0xffff), math.random(0, 0xffff)
  )
end

function request()
  wrk.headers["Idempotency-Key"] = idempotency_key()
  return wrk.format()
end

-- Delete this hook (and the counts aggregation in done) if you don't need the
-- per-status breakdown: it calls into Lua on every response and costs throughput.
function response(status, headers, body)
  counts[status] = (counts[status] or 0) + 1
end

function done(summary, latency, requests)
  local totals = {}
  for _, thread in ipairs(threads) do
    local c = thread:get("counts")
    if c then
      for status, n in pairs(c) do
        totals[status] = (totals[status] or 0) + n
      end
    end
  end

  local seconds = summary.duration / 1e6
  io.write(string.format("\nsent %d requests in %.2fs (%.0f rps)\n",
    summary.requests, seconds, summary.requests / seconds))

  local statuses = {}
  for status in pairs(totals) do table.insert(statuses, status) end
  table.sort(statuses)
  for _, status in ipairs(statuses) do
    io.write(string.format("%d: %d\n", status, totals[status]))
  end

  local e = summary.errors
  local labels = {
    {"connect", e.connect}, {"read", e.read}, {"write", e.write},
    {"timeout", e.timeout}, {"status", e.status},
  }
  for _, pair in ipairs(labels) do
    if pair[2] > 0 then
      io.write(string.format("%s errors: %d\n", pair[1], pair[2]))
    end
  end

  io.write(string.format("latency  p50 %.1fms  p95 %.1fms  p99 %.1fms  max %.1fms\n",
    latency:percentile(50) / 1000, latency:percentile(95) / 1000,
    latency:percentile(99) / 1000, latency.max / 1000))
end
