"""Centralized configuration for Noka JUDGE Backend."""
import os
from functools import lru_cache
from typing import List

from pydantic import BaseModel


class Settings(BaseModel):
    app_name: str
    app_env: str
    secret_key: str
    access_token_expire_minutes: int
    cors_origins: str
    database_url: str
    redis_url: str
    storage_backend: str
    storage_local_path: str
    s3_endpoint_url: str
    s3_bucket_name: str
    s3_access_key: str
    s3_secret_key: str
    s3_region: str
    judge_mode: str
    judge_dispatch_mode: str
    judge_max_concurrent_threads: int
    rate_limit_requests_per_minute: int
    submit_rate_limit_per_minute: int
    max_upload_size_mb: int
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    @property
    def cors_origin_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    default_storage = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage")
    )
    return Settings(
        app_name=os.getenv("APP_NAME", "Noka JUDGE"),
        app_env=os.getenv("APP_ENV", "development"),
        secret_key=os.getenv("SECRET_KEY", "dev-insecure-change-in-production-noka-judge-key"),
        access_token_expire_minutes=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720")),
        cors_origins=os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://localhost:3000,http://localhost"
        ),
        database_url=os.getenv(
            "DATABASE_URL",
            f"sqlite:///{os.path.join(default_storage, 'noka_judge.db')}",
        ),
        redis_url=os.getenv("REDIS_URL", ""),
        storage_backend=os.getenv("STORAGE_BACKEND", "local"),
        storage_local_path=os.getenv("STORAGE_LOCAL_PATH", default_storage),
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL", ""),
        s3_bucket_name=os.getenv("S3_BUCKET_NAME", ""),
        s3_access_key=os.getenv("S3_ACCESS_KEY", ""),
        s3_secret_key=os.getenv("S3_SECRET_KEY", ""),
        s3_region=os.getenv("S3_REGION", "auto"),
        judge_mode=os.getenv("JUDGE_MODE", "local_posix"),
        judge_dispatch_mode=os.getenv("JUDGE_DISPATCH_MODE", "auto"),
        judge_max_concurrent_threads=max(
            1, int(os.getenv("JUDGE_MAX_CONCURRENT_THREADS", "1"))
        ),
        rate_limit_requests_per_minute=int(os.getenv("RATE_LIMIT_REQUESTS_PER_MINUTE", "240")),
        submit_rate_limit_per_minute=int(os.getenv("SUBMIT_RATE_LIMIT_PER_MINUTE", "30")),
        max_upload_size_mb=int(os.getenv("MAX_UPLOAD_SIZE_MB", "50")),
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash",
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
    )
