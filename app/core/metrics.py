import logging
import time

from fastapi import Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

logger = logging.getLogger(__name__)

# HTTP metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

# WebSocket metrics
websocket_connections_total = Counter(
    "websocket_connections_total", "Total number of WebSocket connections", ["chat_id"]
)

websocket_connections_active = Gauge(
    "websocket_connections_active",
    "Number of active WebSocket connections",
    ["chat_id"],
)

websocket_messages_received = Counter(
    "websocket_messages_received_total",
    "Total number of WebSocket messages received",
    ["chat_id"],
)

websocket_messages_sent = Counter(
    "websocket_messages_sent_total",
    "Total number of WebSocket messages sent",
    ["chat_id"],
)

# Message metrics
messages_sent_total = Counter(
    "messages_sent_total", "Total number of messages sent", ["chat_id", "is_group"]
)

# Database metrics
db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1),
)

# Celery metrics
celery_tasks_total = Counter(
    "celery_tasks_total",
    "Total number of Celery tasks executed",
    ["task_name", "status"],
)

celery_task_duration_seconds = Histogram(
    "celery_task_duration_seconds",
    "Celery task duration in seconds",
    ["task_name"],
    buckets=(0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10, 30, 60),
)

celery_queue_length = Gauge(
    "celery_queue_length", "Current length of Celery task queue", ["queue_name"]
)

# System metrics (optional)
active_chats_gauge = Gauge(
    "active_chats_gauge", "Number of chats with active connections"
)


# Helper function to expose metrics endpoint
async def metrics_endpoint():
    """Endpoint for Prometheus to scrape metrics."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Context managers for tracking durations
class TrackTime:
    """Context manager to track execution time."""

    def __init__(self, metric: Histogram, labels: dict = None):
        self.metric = metric
        self.labels = labels or {}
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        self.metric.labels(**self.labels).observe(duration)
