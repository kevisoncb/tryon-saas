from __future__ import annotations

import redis
from rq import Queue

from config import REDIS_URL

if not REDIS_URL:
    raise RuntimeError("REDIS_URL not set. Create backend/.env based on .env.example")


def get_queue() -> Queue:
    conn = redis.from_url(REDIS_URL)
    return Queue("tryon", connection=conn)
