"""In-memory sliding window rate limiter and security headers middleware."""
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.app.core.config import get_settings


class SecurityAndRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app) -> None:
        super().__init__(app)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._submit_hits: Dict[str, Deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_settings()
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()

        if settings.app_env != "test":
            bucket = self._hits[ip]
            while bucket and now - bucket[0] > 60.0:
                bucket.popleft()
            if len(bucket) >= settings.rate_limit_requests_per_minute:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please try again shortly."},
                )
            bucket.append(now)

            if request.method == "POST" and request.url.path.rstrip("/") == "/api/v1/submissions":
                sb = self._submit_hits[ip]
                while sb and now - sb[0] > 60.0:
                    sb.popleft()
                if len(sb) >= settings.submit_rate_limit_per_minute:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Submission rate limit exceeded. Wait a moment."},
                    )
                sb.append(now)

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
