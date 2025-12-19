from __future__ import annotations

import time
from collections import defaultdict, deque


class SimpleRateLimiter:
    def __init__(self, rpm_limit_default: int = 60):
        self.rpm_default = rpm_limit_default
        self.hits = defaultdict(deque)

    def allow(self, api_key: str, rpm_limit: int | None = None) -> bool:
        limit = rpm_limit or self.rpm_default
        now = time.time()
        q = self.hits[api_key]

        # remove >60s
        while q and now - q[0] > 60:
            q.popleft()

        if len(q) >= limit:
            return False

        q.append(now)
        return True
