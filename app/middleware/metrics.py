import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.metrics import http_request_duration_seconds, http_requests_total


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to track HTTP request metrics."""

    async def dispatch(self, request: Request, call_next):
        # Extract endpoint path (without query parameters)
        endpoint = request.url.path

        # Skip metrics endpoint to avoid recursion
        if endpoint == "/metrics":
            return await call_next(request)

        # Track request duration
        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Record metrics
            http_requests_total.labels(
                method=request.method, endpoint=endpoint, status=response.status_code
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method, endpoint=endpoint
            ).observe(duration)

            return response

        except Exception as e:
            # Record failed requests (500 errors)
            duration = time.time() - start_time
            http_requests_total.labels(
                method=request.method, endpoint=endpoint, status=500
            ).inc()

            http_request_duration_seconds.labels(
                method=request.method, endpoint=endpoint
            ).observe(duration)

            raise
