"""Judge Job Queue abstraction: Redis in production, semaphore-throttled threads in stateless/cloud dev & inline in tests."""
import gc
import json
import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from backend.app.core.config import get_settings
from backend.app.core.database import Database
from backend.app.core.storage import BaseStorage

logger = logging.getLogger("noka.queue")

_semaphore_lock = threading.Lock()
_judge_semaphore: Optional[threading.BoundedSemaphore] = None
_judge_semaphore_limit: Optional[int] = None


def get_judge_semaphore() -> threading.BoundedSemaphore:
    """
    Returns a process-wide BoundedSemaphore limiting concurrent Judge executions
    (g++ compilations + sandbox runs) to JUDGE_MAX_CONCURRENT_THREADS (default: 1).
    Prevents OOMKilled crashes on memory-constrained 512 MB containers when 20-30
    students submit C++ code simultaneously.
    """
    global _judge_semaphore, _judge_semaphore_limit
    limit = max(1, int(get_settings().judge_max_concurrent_threads))
    with _semaphore_lock:
        if _judge_semaphore is None or _judge_semaphore_limit != limit:
            _judge_semaphore = threading.BoundedSemaphore(limit)
            _judge_semaphore_limit = limit
        return _judge_semaphore


def reset_judge_semaphore() -> None:
    """Resets the cached semaphore (used in tests when env config changes)."""
    global _judge_semaphore, _judge_semaphore_limit
    with _semaphore_lock:
        _judge_semaphore = None
        _judge_semaphore_limit = None


@contextmanager
def judge_execution_slot() -> Iterator[None]:
    """Serializes/throttles heavy compile+run work across submit, run-sample, and generator."""
    sem = get_judge_semaphore()
    sem.acquire()
    try:
        yield
    finally:
        sem.release()
        gc.collect()


def _run_serialized_submission(
    submission_id: int,
    db: Database,
    storage: BaseStorage,
) -> None:
    from backend.app.services.submission_service import process_submission_job

    with judge_execution_slot():
        try:
            process_submission_job(submission_id, db, storage)
        except Exception as exc:
            logger.exception("Failed judging submission #%s: %s", submission_id, exc)
            try:
                db.execute(
                    """
                    UPDATE submissions
                    SET status = 'COMPLETED',
                        verdict = 'IE',
                        compile_output = %s,
                        judged_at = %s
                    WHERE id = %s AND status != 'COMPLETED'
                    """,
                    (f"Internal Judge Error: {exc}", datetime.now(timezone.utc).isoformat(), submission_id),
                )
            except Exception:
                logger.exception("Failed marking submission #%s as IE.", submission_id)


def enqueue_submission_job(
    submission_id: int,
    db: Database,
    storage: BaseStorage,
) -> str:
    """
    Dispatches a submission to the independent Judge Worker via Redis queue in production.
    In stateless single-container deployments (e.g. Railway Free 512 MB RAM) or local dev
    where Redis/external worker is not used, runs in a background thread strictly throttled
    by JUDGE_MAX_CONCURRENT_THREADS (default: 1) so queued submissions never cause OOM.
    """
    settings = get_settings()
    mode = settings.judge_dispatch_mode

    if mode in ("auto", "redis") and settings.redis_url:
        try:
            import redis  # type: ignore

            client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
            client.rpush("noka:judge:submissions", json.dumps({"submission_id": submission_id}))
            return "redis"
        except Exception:
            if mode == "redis":
                raise

    if mode == "inline" or settings.app_env == "test":
        _run_serialized_submission(submission_id, db, storage)
        return "inline"

    t = threading.Thread(
        target=_run_serialized_submission,
        args=(submission_id, db, storage),
        daemon=True,
        name=f"judge-sub-{submission_id}",
    )
    t.start()
    return "thread"
