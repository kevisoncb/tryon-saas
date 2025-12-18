import time
from collections import defaultdict, deque

class InMemoryRateLimiter:
    """
    Rate limit simples por janela deslizante (sliding window).
    Bom para dev/local e 1 instância.
    Em produção, substitui por Redis.
    """
    def __init__(self):
        self._hits = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        q = self._hits[key]

        # remove hits fora da janela
        cutoff = now - window_seconds
        while q and q[0] < cutoff:
            q.popleft()

        if len(q) >= limit:
            return False

        q.append(now)
        return True
