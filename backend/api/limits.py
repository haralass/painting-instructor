"""
Upload limits, per-IP rate limiting and queue visibility.

Sized for the real deployment: one Mac behind a Cloudflare tunnel, a handful
of friends, one Celery worker. The point is not to survive an attack — access
control is Cloudflare Access in front of the tunnel — it is that three people
painting at once get honest queue positions instead of a spinner, and that a
mistyped upload fails with a sentence instead of a 500.

State is in-process on purpose: a single uvicorn process serves this instance,
so a dict is the right amount of machinery. Under multiple workers each would
keep its own counters, which is documented rather than solved.
"""
from __future__ import annotations

import os
import time
from collections import deque

from fastapi import HTTPException, UploadFile


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "")))
    except (TypeError, ValueError):
        return default


# ── Uploads ──────────────────────────────────────────────────────────────────

MAX_UPLOAD_MB = _env_int("MAX_UPLOAD_MB", 25)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}

# Leading bytes per accepted format. Content-Type is client-supplied and a
# phone will happily label anything image/jpeg, so the bytes decide.
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
)


def _looks_like_image(head: bytes) -> bool:
    if any(head.startswith(sig) for sig, _ in _MAGIC):
        return True
    # RIFF....WEBP  and  ....ftyp(heic|heix|hevc|mif1)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return True
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1"):
        return True
    return False


async def read_image_upload(file: UploadFile, *, field: str = "file") -> bytes:
    """Read an uploaded image, enforcing type and size with clear errors.

    Reads in chunks and stops at the limit, so an oversized upload cannot be
    buffered into memory in full just to be rejected.
    """
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            415,
            f"{field}: unsupported image type {file.content_type or 'unknown'!r}. "
            f"Use JPEG, PNG, WebP or HEIC.",
        )

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1 << 20)  # 1 MiB
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                413,
                f"{field}: image is larger than {MAX_UPLOAD_MB} MB. "
                f"Export it smaller and try again — a photo around 2000px on "
                f"the long edge is plenty for the analysis.",
            )
        chunks.append(chunk)

    data = b"".join(chunks)
    if not data:
        raise HTTPException(400, f"{field}: the uploaded file is empty.")
    if not _looks_like_image(data[:16]):
        raise HTTPException(
            415,
            f"{field}: that file is not a readable image, whatever it is named. "
            f"Use JPEG, PNG, WebP or HEIC.",
        )
    return data


# ── Per-IP rate limiting ─────────────────────────────────────────────────────

# Starting a job costs minutes of ML on one worker, so the budget is per hour,
# not per second. Generous for a person, firm against a loop.
RATE_LIMIT_MAX = _env_int("RATE_LIMIT_JOBS_PER_HOUR", 20)
RATE_LIMIT_WINDOW_SEC = 3600


class RateLimiter:
    """Sliding-window counter keyed by client IP."""

    def __init__(self, max_events: int, window_sec: int) -> None:
        self.max_events = max_events
        self.window_sec = window_sec
        self._hits: dict[str, deque[float]] = {}

    def _window(self, key: str, now: float) -> deque[float]:
        window = self._hits.setdefault(key, deque())
        cutoff = now - self.window_sec
        while window and window[0] < cutoff:
            window.popleft()
        return window

    def ensure_capacity(self, key: str) -> None:
        """Raise 429 if `key` has no budget left. Records nothing."""
        now = time.monotonic()
        window = self._window(key, now)
        if len(window) >= self.max_events:
            retry_after = int(window[0] + self.window_sec - now) + 1
            raise HTTPException(
                429,
                f"That is {self.max_events} paintings started in the last hour "
                f"from this address — the machine analysing them is one Mac. "
                f"Try again in about {max(1, retry_after // 60)} minute(s).",
                headers={"Retry-After": str(max(1, retry_after))},
            )

    def record(self, key: str) -> None:
        """Charge one accepted unit of work to `key`."""
        now = time.monotonic()
        self._window(key, now).append(now)

        # Keep the dict from growing without bound on a long-lived process.
        if len(self._hits) > 512:
            cutoff = now - self.window_sec
            for k in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                self._hits.pop(k, None)

    def check(self, key: str) -> None:
        """Capacity check plus record, for callers with nothing to validate."""
        self.ensure_capacity(key)
        self.record(key)


job_limiter = RateLimiter(RATE_LIMIT_MAX, RATE_LIMIT_WINDOW_SEC)
# Critique is plain CV and returns in about a second — looser, still bounded.
critique_limiter = RateLimiter(_env_int("RATE_LIMIT_CRITIQUES_PER_HOUR", 120),
                               RATE_LIMIT_WINDOW_SEC)


def client_ip(request) -> str:
    """Best-effort client identity behind the tunnel.

    Cloudflare sets CF-Connecting-IP; a plain reverse proxy sets
    X-Forwarded-For. Falls back to the socket peer for direct local use.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Queue visibility ─────────────────────────────────────────────────────────

def queue_depth() -> int | None:
    """How many jobs are waiting to be picked up, or None if unknowable.

    Reads the broker list directly: Celery has no cheap "position of this
    task" call, and the worker only reports on tasks it has already started.
    """
    try:
        from ..workers.tasks import celery_app

        with celery_app.connection_or_acquire() as conn:
            return int(conn.default_channel.client.llen("celery"))
    except Exception:
        return None


def queue_position(job_id: str) -> int | None:
    """1-based position of a queued job, or None if it is not waiting."""
    try:
        import json as _json

        from ..workers.tasks import celery_app

        with celery_app.connection_or_acquire() as conn:
            pending = conn.default_channel.client.lrange("celery", 0, -1)
    except Exception:
        return None

    # Celery pushes newest to the head, so the tail is served first.
    for offset, raw in enumerate(reversed(pending or [])):
        try:
            body = _json.loads(raw)
            if body.get("headers", {}).get("id") == job_id:
                return offset + 1
        except Exception:
            continue
    return None
