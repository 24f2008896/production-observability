
import json
import os
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from threading import Lock

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from prometheus_client import Counter, CONTENT_TYPE_LATEST, generate_latest


app = FastAPI(title="Production Observability API")

# Replace this with the email assigned in your question.
EMAIL = os.getenv("ASSIGNED_EMAIL", "24f2008896@ds.study.iitm.ac.in")

# Prometheus Counter: exported metric name is http_requests_total.
REQUEST_COUNTER = Counter(
    "http_requests",
    "Total number of HTTP requests received by this service",
)

# Store recent JSON log entries in memory.
LOG_ENTRIES = deque(maxlen=1000)
LOG_LOCK = Lock()

START_TIME = time.monotonic()


def write_log(level, path, request_id, **extra):
    """Create and store one structured JSON log entry."""
    entry = {
        "level": level,
        "ts": datetime.now(timezone.utc).isoformat(),
        "path": path,
        "request_id": request_id,
        **extra,
    }

    with LOG_LOCK:
        LOG_ENTRIES.append(entry)

    # Also print the log as JSON for Render's log viewer.
    print(json.dumps(entry), flush=True)


@app.middleware("http")
async def observe_requests(request: Request, call_next):
    """Count and log every incoming HTTP request."""
    REQUEST_COUNTER.inc()

    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    path = request.url.path
    started = time.monotonic()

    try:
        response = await call_next(request)
        write_log(
            "INFO",
            path,
            request_id,
            method=request.method,
            status_code=response.status_code,
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        response.headers["X-Request-ID"] = request_id
        return response

    except Exception as exc:
        write_log(
            "ERROR",
            path,
            request_id,
            method=request.method,
            error=str(exc),
        )
        raise


@app.get("/")
def root():
    return {"message": "Production Observability API is running"}


@app.get("/work")
def work(n: int = Query(..., ge=0, le=1000000)):
    """Perform K units of work and return the required response."""
    done = 0

    for _ in range(n):
        done += 1

    return {"email": EMAIL, "done": done}


@app.get("/metrics")
def metrics():
    """Return live Prometheus metrics in text exposition format."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@app.get("/healthz")
def healthz():
    """Report service health and seconds since startup."""
    uptime = max(0.0, time.monotonic() - START_TIME)
    return {"status": "ok", "uptime_s": float(uptime)}


@app.get("/logs/tail")
def logs_tail(limit: int = Query(10, ge=1, le=1000)):
    """Return the most recent log entries as a JSON array."""
    with LOG_LOCK:
        entries = list(LOG_ENTRIES)[-limit:]

    entries.reverse()
    return entries
