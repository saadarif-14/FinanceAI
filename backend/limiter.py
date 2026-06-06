"""
Redis-backed rate limiting and TTL cache.

Reads REDIS_URL from environment (default: redis://localhost:6379/0).
Falls back to a simple in-memory store if Redis is unreachable, so the
app starts cleanly even without Redis running locally.
"""
import json
import os
import time
from threading import Lock
from fastapi import HTTPException

AI_LIMIT = 30    # max AI requests
AI_WINDOW = 60   # per N seconds

# ── Redis connection ──────────────────────────────────────────────────────────

_redis = None
_redis_ok = False


def _get_redis():
    global _redis, _redis_ok
    if _redis is not None:
        return _redis if _redis_ok else None
    try:
        import redis as redis_lib
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis = redis_lib.from_url(url, decode_responses=True, socket_connect_timeout=2)
        _redis.ping()
        _redis_ok = True
        print(f"[limiter] Redis connected: {url}")
    except Exception as e:
        _redis_ok = False
        print(f"[limiter] Redis unavailable ({e}), falling back to in-memory store")
    return _redis if _redis_ok else None


# ── In-memory fallback ────────────────────────────────────────────────────────

_fb_lock = Lock()
_fb_windows: dict = {}   # user_id → [timestamps]
_fb_cache: dict = {}     # key → (expires_at, value)


# ── Rate limiter ──────────────────────────────────────────────────────────────

def check_rate_limit(user_id: str, limit: int = AI_LIMIT, window: int = AI_WINDOW) -> None:
    """Raise HTTP 429 if user has exceeded `limit` requests in the last `window` seconds."""
    r = _get_redis()

    if r:
        # Redis sliding window using a sorted set keyed by user
        key = f"rl:{user_id}"
        now = time.time()
        cutoff = now - window
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, cutoff)         # remove old entries
        pipe.zcard(key)                                # count remaining
        pipe.zadd(key, {str(now): now})                # add this request
        pipe.expire(key, window + 5)                   # auto-expire the key
        _, count, *_ = pipe.execute()
        if count >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Too many requests — max {limit} AI messages per {window}s. Please wait.",
            )
    else:
        # In-memory fallback (single-process only)
        now = time.monotonic()
        cutoff = now - window
        with _fb_lock:
            ts = [t for t in _fb_windows.get(user_id, []) if t > cutoff]
            if len(ts) >= limit:
                raise HTTPException(
                    status_code=429,
                    detail=f"Too many requests — max {limit} AI messages per {window}s. Please wait.",
                )
            ts.append(now)
            _fb_windows[user_id] = ts


# ── TTL cache ─────────────────────────────────────────────────────────────────

def cache_get(key: str):
    r = _get_redis()
    if r:
        raw = r.get(f"cache:{key}")
        return json.loads(raw) if raw else None
    else:
        with _fb_lock:
            entry = _fb_cache.get(key)
            if entry and time.monotonic() < entry[0]:
                return entry[1]
            return None


def cache_set(key: str, value, ttl: int = 60) -> None:
    r = _get_redis()
    if r:
        r.setex(f"cache:{key}", ttl, json.dumps(value, default=str))
    else:
        with _fb_lock:
            _fb_cache[key] = (time.monotonic() + ttl, value)


def cache_invalidate(key: str) -> None:
    r = _get_redis()
    if r:
        r.delete(f"cache:{key}")
    else:
        with _fb_lock:
            _fb_cache.pop(key, None)
