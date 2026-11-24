"""Unit tests for stateless cloud hardening: Semaphore anti-OOM queue, Cloudflare R2 S3Storage, and temp cleanup."""
import os
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


class TestStatelessHardening(unittest.TestCase):
    def setUp(self) -> None:
        from backend.app.core.config import get_settings
        from backend.app.core.queue import reset_judge_semaphore

        get_settings.cache_clear()
        reset_judge_semaphore()

    def tearDown(self) -> None:
        from backend.app.core.config import get_settings
        from backend.app.core.queue import reset_judge_semaphore

        os.environ.pop("JUDGE_MAX_CONCURRENT_THREADS", None)
        get_settings.cache_clear()
        reset_judge_semaphore()

    def test_semaphore_limits_concurrent_judge_threads_to_one(self) -> None:
        os.environ["JUDGE_MAX_CONCURRENT_THREADS"] = "1"
        from backend.app.core.config import get_settings
        from backend.app.core.queue import judge_execution_slot, reset_judge_semaphore

        get_settings.cache_clear()
        reset_judge_semaphore()

        active = 0
        peak_active = 0
        completed = 0
        lock = threading.Lock()

        def worker() -> None:
            nonlocal active, peak_active, completed
            with judge_execution_slot():
                with lock:
                    active += 1
                    peak_active = max(peak_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1
                    completed += 1

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(completed, 6)
        self.assertEqual(peak_active, 1)

    def test_semaphore_releases_on_exception(self) -> None:
        os.environ["JUDGE_MAX_CONCURRENT_THREADS"] = "1"
        from backend.app.core.config import get_settings
        from backend.app.core.queue import judge_execution_slot, reset_judge_semaphore

        get_settings.cache_clear()
        reset_judge_semaphore()

        with self.assertRaises(RuntimeError):
            with judge_execution_slot():
                raise RuntimeError("boom")

        acquired = False
        with judge_execution_slot():
            acquired = True
        self.assertTrue(acquired)

    def test_s3_storage_cloudflare_r2_config_and_missing_key(self) -> None:
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"hello r2"
        mock_client.get_object.return_value = {"Body": mock_body}

        with patch("boto3.client", return_value=mock_client) as mock_boto:
            from backend.app.core.storage import S3Storage

            st = S3Storage(
                endpoint_url="https://acc123.r2.cloudflarestorage.com/",
                bucket="noka-bucket",
                access_key="ak",
                secret_key="sk",
                region_name="auto",
            )

            _, kwargs = mock_boto.call_args
            self.assertEqual(kwargs["endpoint_url"], "https://acc123.r2.cloudflarestorage.com")
            self.assertEqual(kwargs["region_name"], "auto")
            cfg = kwargs["config"]
            self.assertEqual(cfg.signature_version, "s3v4")
            self.assertEqual(getattr(cfg, "request_checksum_calculation", None), "when_required")
            self.assertEqual(getattr(cfg, "response_checksum_validation", None), "when_required")

            # Key normalization & put/get
            self.assertEqual(st.put_bytes("/testcases/p_1/tc_1.in", b"1 2\n"), "testcases/p_1/tc_1.in")
            mock_client.put_object.assert_called_once_with(
                Bucket="noka-bucket", Key="testcases/p_1/tc_1.in", Body=b"1 2\n"
            )
            self.assertEqual(st.get_bytes("/testcases/p_1/tc_1.in"), b"hello r2")
            mock_body.close.assert_called_once()

            # Missing key returns b"" instead of raising
            mock_client.get_object.side_effect = ClientError(
                {"Error": {"Code": "NoSuchKey"}, "ResponseMetadata": {"HTTPStatusCode": 404}},
                "GetObject",
            )
            self.assertEqual(st.get_bytes("missing/key.txt"), b"")

    def test_cleanup_stale_exec_dirs(self) -> None:
        from judge.sandbox import runner

        with tempfile.TemporaryDirectory() as tmp:
            stale = os.path.join(tmp, "noka_sub_stale123")
            keep = os.path.join(tmp, "other_dir")
            os.makedirs(stale)
            os.makedirs(keep)
            with open(os.path.join(stale, "solution.cpp"), "w", encoding="utf-8") as f:
                f.write("int main(){}")

            with patch.object(runner, "get_exec_work_root", return_value=tmp):
                removed = runner.cleanup_stale_exec_dirs()
            self.assertEqual(removed, 1)
            self.assertFalse(os.path.exists(stale))
            self.assertTrue(os.path.exists(keep))


if __name__ == "__main__":
    unittest.main()
