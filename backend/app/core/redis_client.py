"""
TridentWear — Redis Integration & Distributed Rate Limiting
Provides centralized rate limiting across multiple uvicorn workers.
Features safe fallback to in-memory sliding window when Redis is unavailable or unconfigured.
"""
import os
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import redis
    from redis.exceptions import RedisError, ConnectionError as RedisConnError
    HAS_REDIS = True
except ImportError:
    redis = None
    RedisError = Exception
    RedisConnError = Exception
    HAS_REDIS = False

_redis_client = None
_redis_initialized = False

def get_redis_client():
    """Returns the singleton Redis client if REDIS_URL is configured and available."""
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client

    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url or not HAS_REDIS:
        _redis_client = None
        _redis_initialized = True
        return None

    try:
        pool = redis.ConnectionPool.from_url(
            redis_url,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
            max_connections=20
        )
        client = redis.Redis(connection_pool=pool)
        # Test connection with quick ping
        client.ping()
        _redis_client = client
        logger.info("[REDIS] Successfully connected to Redis at %s", redis_url.split("@")[-1])
    except Exception as exc:
        logger.warning("[REDIS] Could not connect to Redis (%s). Falling back to in-memory mode.", exc)
        _redis_client = None

    _redis_initialized = True
    return _redis_client


def check_rate_limit(
    key: str,
    max_requests: int = 15,
    window_seconds: int = 60,
    in_memory_store: Optional[dict] = None
) -> Tuple[bool, int]:
    """
    Checks rate limit using Redis sliding window if available,
    falling back safely to in_memory_store.
    Returns (is_allowed: bool, current_count: int).
    """
    now = time.time()
    client = get_redis_client()

    if client is not None:
        try:
            redis_key = f"rate_limit:{key}"
            pipe = client.pipeline()
            # Remove timestamps outside the sliding window
            pipe.zremrangebyscore(redis_key, 0, now - window_seconds)
            # Add current timestamp with unique member
            pipe.zadd(redis_key, {f"{now}:{time.time_ns()}": now})
            # Count elements in sliding window
            pipe.zcard(redis_key)
            # Set key expiry to ensure cleanup
            pipe.expire(redis_key, window_seconds + 5)
            results = pipe.execute()
            
            current_count = results[2]
            allowed = current_count <= max_requests
            return allowed, current_count
        except (RedisError, RedisConnError) as err:
            logger.warning("[REDIS] Rate limiter error (%s), using in-memory fallback.", err)

    # In-memory sliding window fallback
    if in_memory_store is None:
        in_memory_store = {}

    if key not in in_memory_store:
        in_memory_store[key] = []

    # Clean stale entries
    in_memory_store[key] = [t for t in in_memory_store[key] if now - t < window_seconds]

    if len(in_memory_store[key]) >= max_requests:
        return False, len(in_memory_store[key])

    in_memory_store[key].append(now)
    return True, len(in_memory_store[key])


def get_redis_health() -> dict:
    """Returns Redis connection health status."""
    redis_url = os.getenv("REDIS_URL", "").strip()
    if not redis_url:
        return {"status": "unconfigured", "driver_installed": HAS_REDIS}

    if not HAS_REDIS:
        return {"status": "driver_missing", "error": "redis Python package not installed"}

    client = get_redis_client()
    if client is None:
        return {"status": "unavailable", "url": redis_url.split("@")[-1]}

    try:
        client.ping()
        return {"status": "connected", "url": redis_url.split("@")[-1]}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}
