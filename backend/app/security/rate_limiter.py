import time
from collections import defaultdict
from fastapi import HTTPException


class SimpleRateLimiter:
    """
    Limiter simples em memória.
    Em produção, isso vira Redis/Upstash, mas mantém o código limpo agora.
    """
    def __init__(self):
        self._buckets = defaultdict(lambda: {"tokens": 0.0, "ts": time.time()})

    def check(self, key: str, rpm_limit: int):
        if rpm_limit <= 0:
            return

        now = time.time()
        b = self._buckets[key]
        elapsed = now - b["ts"]
        b["ts"] = now

        refill_per_sec = rpm_limit / 60.0
        b["tokens"] = min(float(rpm_limit), b["tokens"] + elapsed * refill_per_sec)

        if b["tokens"] < 1.0:
            raise HTTPException(status_code=429, detail={
                "error_code": "RATE_LIMIT",
                "message": "Too many requests. Slow down.",
                "details": {"rpm_limit": rpm_limit}
            })

        b["tokens"] -= 1.0
