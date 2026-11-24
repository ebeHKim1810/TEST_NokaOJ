"""Storage abstraction supporting Local Filesystem and S3-compatible object storage (Cloudflare R2 / AWS S3 / MinIO)."""
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
    """S3-compatible storage backend (Cloudflare R2 / AWS S3 / MinIO)."""

    def __init__(
        self,
        endpoint_url: str,
        bucket: str,
        access_key: str,
        secret_key: str,
        region_name: str = "auto",
    ) -> None:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore

        self.bucket = bucket.strip()
        clean_endpoint = (endpoint_url or "").strip().rstrip("/") or None
        clean_region = (region_name or "auto").strip()

        # Cloudflare R2 requires SigV4, region="auto", and disabling modern boto3>=1.36
        # automatic CRC32 checksum headers unless explicitly required by the operation.
        base_cfg = {
            "region_name": clean_region,
            "signature_version": "s3v4",
            "s3": {"addressing_style": "path"},
            "retries": {"max_attempts": 3, "mode": "standard"},
        }
        try:
            cfg = Config(
                **base_cfg,
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            )
        except TypeError:
            cfg = Config(**base_cfg)

        self.client = boto3.client(
            "s3",
            endpoint_url=clean_endpoint,
            aws_access_key_id=access_key.strip(),
            aws_secret_access_key=secret_key.strip(),
            region_name=clean_region,
            config=cfg,
        )

    @staticmethod
    def _clean_key(key: str) -> str:
        clean = key.lstrip("/").replace("..", "")
        if not clean:
            raise ValueError("Invalid empty storage key.")
        return clean

    def put_bytes(self, key: str, data: bytes) -> str:
        clean = self._clean_key(key)
        self.client.put_object(Bucket=self.bucket, Key=clean, Body=data)
        return clean

    def get_bytes(self, key: str) -> bytes:
        from botocore.exceptions import ClientError  # type: ignore

        clean = self._clean_key(key)
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=clean)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
            if code in ("NoSuchKey", "404", "NotFound") or status == 404:
                return b""
            raise
        body = resp["Body"]
        try:
            return body.read()
        finally:
            body.close()

    def delete(self, key: str) -> None:
        from botocore.exceptions import ClientError  # type: ignore

        clean = self._clean_key(key)
        try:
            self.client.delete_object(Bucket=self.bucket, Key=clean)
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            status = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0) or 0)
            if code in ("NoSuchKey", "404", "NotFound") or status == 404:
                return
            raise


_storage_instance: Optional[BaseStorage] = None


def get_storage() -> BaseStorage:
    global _storage_instance
    if _storage_instance is None:
        s = get_settings()
        if s.storage_backend.lower() == "s3" and s.s3_bucket_name:
            _storage_instance = S3Storage(
                endpoint_url=s.s3_endpoint_url,
                bucket=s.s3_bucket_name,
                access_key=s.s3_access_key,
                secret_key=s.s3_secret_key,
                region_name=s.s3_region,
            )
        else:
            _storage_instance = LocalFileStorage(s.storage_local_path)
    return _storage_instance


def reset_storage_instance(base_dir: Optional[str] = None) -> BaseStorage:
    global _storage_instance
    if base_dir is not None:
        _storage_instance = LocalFileStorage(base_dir)
        return _storage_instance
    _storage_instance = None
    return get_storage()
