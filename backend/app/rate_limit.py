"""In-process rate limiting for the unauthenticated auth endpoints (brief §4.5).

A dict of recent hit timestamps is enough here: OppTrail runs as a single
process in a single container (ADR 0002's deployment model), so there is no
second worker to share state with. If that ever changes, this is the one place
that has to move to shared storage.
"""

import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, status
from starlette.requests import Request

# Above this many distinct keys, expired ones are swept before a new key is
# added, so a flood from many source addresses cannot grow the dict without
# bound.
SWEEP_THRESHOLD = 1024


class RateLimiter:
    """Sliding window over the last `window_seconds`, keyed by caller.

    The clock is injected so tests can advance time exactly rather than sleep
    (brief §6.5: deterministic time, no sleeps).
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def reset(self) -> None:
        self._hits.clear()

    def check(self, key: str, max_attempts: int, window_seconds: int) -> None:
        now = self._clock()
        cutoff = now - window_seconds

        if key not in self._hits and len(self._hits) >= SWEEP_THRESHOLD:
            self._sweep(cutoff)

        hits = self._hits.setdefault(key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= max_attempts:
            retry_after = int(hits[0] + window_seconds - now) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many attempts. Try again later.",
                headers={"Retry-After": str(retry_after)},
            )

        hits.append(now)

    def _sweep(self, cutoff: float) -> None:
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]


auth_rate_limiter = RateLimiter()


def client_key(request: Request, scope: str) -> str:
    """Source address plus the endpoint, so a login flood cannot lock out
    signups (and vice versa). `request.client` is None for ASGI transports that
    report no peer, which the test client does not use but the type allows.
    """
    host = request.client.host if request.client else "unknown"
    return f"{scope}:{host}"
