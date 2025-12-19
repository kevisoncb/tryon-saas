# backend/app/security/rate_limiter.py
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock
from typing import Dict

from fastapi import HTTPException


class SimpleRateLimiter:
    """
    Limiter simples em memória (token bucket).
    Em produção, isso vira Redis/Upstash, mas mantém o código limpo agora. :contentReference[oaicite:5]{index=5}
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._buckets: Dict[str, dict] = defaultdict(self._new_bucket)

    @staticmethod
    def _new_bucket() -> dict:
        # Começa com tokens "cheios" para permitir burst inicial controlado.
        return {"tokens": 0.0, "ts": time.monotonic(), "cap": 0.0}

    def check(self, key: str, rpm_limit: int) -> None:
        """
        Consome 1 token por request. Recarrega a uma taxa de rpm_limit / 60 tokens/s.
        """
        if rpm_limit <= 0:
            return

        now = time.monotonic()
        refill_per_sec = float(rpm_limit) / 60.0
        cap = float(rpm_limit)

        with self._lock:
            b = self._buckets[key]

            # Se o limite mudou, ajuste a capacidade e (se era zero) encha
            if b["cap"] != cap:
                b["cap"] = cap
                # Se bucket estava "vazio inicial", dá burst inicial igual ao cap
                if b["tokens"] <= 0.0:
                    b["tokens"] = cap

            elapsed = now - b["ts"]
            b["ts"] = now

            # Refill
            b["tokens"] = min(cap, float(b["tokens"]) + elapsed * refill_per_sec)

            if b["tokens"] < 1.0:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error_code": "RATE_LIMIT",
                        "message": "Too many requests. Slow down.",
                        "details": {"rpm_limit": rpm_limit},
                    },
                )

            b["tokens"] -= 1.0
