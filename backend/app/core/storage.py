"""Storage abstraction supporting Local Filesystem and S3-compatible object storage."""
import os
from abc import ABC, abstractmethod
from typing import Optional

from backend.app.core.config import get_settings


class BaseStorage(ABC):
    @abstractmethod
    def put_bytes(self, key: str, data: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_bytes(self, key: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

    def put_text(self, key: str, text: str) -> str:
        return self.put_bytes(key, text.encode("utf-8"))

    def get_text(self, key: str) -> str:
        return self.get_bytes(key).decode("utf-8", errors="replace")


class LocalFileStorage(BaseStorage):
    def __init__(self, base_dir: str) -> None:
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def _safe_path(self, key: str) -> str:
        clean = key.lstrip("/").replace("..", "")
        full = os.path.abspath(os.path.join(self.base_dir, clean))
        if not full.startswith(self.base_dir):
            raise ValueError("Invalid storage key path traversal attempt.")
        return full

    def put_bytes(self, key: str, data: bytes) -> str:
        path = self._safe_path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        path = self._safe_path(key)
        if not os.path.exists(path):
            return b""
        with open(path, "rb") as f:
            return f.read()

    def delete(self, key: str) -> None:
        path = self._safe_path(key)
        if os.path.exists(path):
            os.remove(path)


class S3Storage(BaseStorage):
    """S3-compatible storage backend (AWS S3 / MinIO / Cloudflare R2)."""

    def __init__(self, endpoint_url: str, bucket: str, access_key: str, secret_key: str) -> None:
        import boto3  # type: ignore

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url or None,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )

    def put_bytes(self, key: str, data: bytes) -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def get_bytes(self, key: str) -> bytes:
        resp = self.client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


_storage_instance: Optional[BaseStorage] = None


def get_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is None:
        s = get_settings()
        if s.storage_backend == "s3" and s.s3_bucket_name:
            _storage_instance = S3Storage(
                s.s3_endpoint_url, s.s3_bucket_name, s.s3_access_key, s.s3_secret_key
            )
        else:
            _storage_instance = LocalFileStorage(s.storage_local_path)
    return _storage_instance


def reset_storage_instance(base_dir: Optional[str] = None) -> BaseStorage:
    global _storage_instance
    _storage_instance = LocalFileStorage(base_dir or get_settings().storage_local_path)
    return _storage_instance
