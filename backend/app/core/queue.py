"""Judge Job Queue abstraction: Redis in production, background worker / inline in local dev & tests."""
import json
import threading
from typing import Optional

from backend.app.core.config import get_settings
from backend.app.core.database import Database
from backend.app.core.storage import BaseStorage


def enqueue_submission_job(
    submission_id: int,
    db: Database,
    storage: BaseStorage,
) -> str:
    """
    Dispatches a submission to the independent Judge Worker via Redis queue in production.
    In local dev or automated test mode where Redis/external worker is not running,
    dispatches cleanly to JudgeEngine (inline in test mode, background thread in local dev).
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

    from backend.app.services.submission_service import process_submission_job

    if mode == "inline" or settings.app_env == "test":
        process_submission_job(submission_id, db, storage)
        return "inline"

    t = threading.Thread(
        target=process_submission_job,
        args=(submission_id, db, storage),
        daemon=True,
    )
    t.start()
    return "thread"
