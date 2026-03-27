from __future__ import annotations

import time

import redis


class SlidingWindowRateLimiter:
    def __init__(self, r: redis.Redis, *, max_calls: int, window_seconds: int) -> None:
        self.r = r
        self.max_calls = max_calls
        self.window_seconds = window_seconds

    def allow(self, key: str) -> tuple[bool, int]:
        """
        Returns (allowed, remaining).
        Uses a ZSET of timestamps (ms) per key.
        """
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - self.window_seconds * 1000
        zkey = f"rl:{key}"
        pipe = self.r.pipeline()
        pipe.zremrangebyscore(zkey, 0, cutoff)
        pipe.zadd(zkey, {str(now_ms): now_ms})
        pipe.zcard(zkey)
        pipe.expire(zkey, self.window_seconds + 5)
        _, _, count, _ = pipe.execute()
        count_i = int(count)
        allowed = count_i <= self.max_calls
        remaining = max(0, self.max_calls - count_i)
        return allowed, remaining

