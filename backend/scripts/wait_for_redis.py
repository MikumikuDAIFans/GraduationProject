"""Wait until Redis is reachable."""

from __future__ import annotations

import os
import sys
import time

import redis


def main() -> int:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    deadline = time.time() + 30
    
    print(f"Connecting to Redis at: {redis_url}")

    while time.time() < deadline:
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            print("✓ Redis is ready.")
            return 0
        except redis.RedisError as e:
            print(f"Waiting for Redis... ({e})")
            time.sleep(1)

    print("✗ Timed out waiting for Redis.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
