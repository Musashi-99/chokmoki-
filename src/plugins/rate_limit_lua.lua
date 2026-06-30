-- Atomic token bucket: HMGET/HMSET on rl:{key}
-- ARGV[1] capacity (burst)
-- ARGV[2] refill_rate per millisecond
-- ARGV[3] now_ms
-- ARGV[4] cost (default 1)
-- ARGV[5] ttl_ms (key expiry)
-- Returns {allowed (0|1), retry_after_ms}

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4]) or 1
local ttl_ms = tonumber(ARGV[5]) or 3600000

if capacity <= 0 or refill_rate <= 0 then
  return {1, 0}
end

local data = redis.call("HMGET", key, "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
  tokens = capacity
  last_refill = now
end

local elapsed = now - last_refill
if elapsed < 0 then
  elapsed = 0
end

tokens = math.min(capacity, tokens + (elapsed * refill_rate))

if tokens < cost then
  local deficit = cost - tokens
  local retry_ms = 0
  if refill_rate > 0 then
    retry_ms = math.ceil(deficit / refill_rate)
  else
    retry_ms = ttl_ms
  end
  redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
  redis.call("PEXPIRE", key, ttl_ms)
  return {0, retry_ms}
end

tokens = tokens - cost
redis.call("HMSET", key, "tokens", tokens, "last_refill", now)
redis.call("PEXPIRE", key, ttl_ms)
return {1, 0}
