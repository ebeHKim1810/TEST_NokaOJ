"""Unit & integration tests for Zero-Disk Problem Auto-Import (.docx, .pdf, image -> Gemini / OpenAI fallback)."""
import io
import json
import os
import tempfile
import unittest
import zipfile
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from backend.app.services.problem_auto_import import (
    MAX_AUTO_IMPORT_BYTES,
    extract_docx_content_in_memory,
)

VALID_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc`\x00\x00"
    b"\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82"
)

VALID_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


def _build_minimal_docx_with_omml_and_table() -> bytes:
    """Builds a real valid .docx archive purely in memory containing text, OMML math, and a sample table."""
    content_types = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document_xml = """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">
  <w:body>
    <w:p>
      <w:r><w:t>Bài toán: Tính tổng </w:t></w:r>
      <m:oMath>
        <m:f>
          <m:num><m:r><m:t>a</m:t></m:r></m:num>
          <m:den><m:r><m:t>b</m:t></m:r></m:den>
        </m:f>
      </m:oMath>
      <w:r><w:t> với </w:t></w:r>
      <m:oMath>
        <m:sSub><m:e><m:r><m:t>a</m:t></m:r></m:e><m:sub><m:r><m:t>i</m:t></m:r></m:sub></m:sSub>
        <m:r><m:t> ≤ </m:t></m:r>
        <m:sSup><m:e><m:r><m:t>10</m:t></m:r></m:e><m:sup><m:r><m:t>9</m:t></m:r></m:sup></m:sSup>
      </m:oMath>
    </w:p>
    <w:tbl>
      <w:tr>
        <w:tc><w:p><w:r><w:t>Sample Input</w:t></w:r></w:p></w:tc>
        <w:tc><w:p><w:r><w:t>Sample Output</w:t></w:r></w:p></w:tc>
      </w:tr>
      <w:tr>
        <w:tc>
          <w:p><w:r><w:t>3</w:t></w:r></w:p>
          <w:p><w:r><w:t>1 2 3</w:t></w:r></w:p>
        </w:tc>
        <w:tc><w:p><w:r><w:t>6</w:t></w:r></w:p></w:tc>
      </w:tr>
    </w:tbl>
  </w:body>
</w:document>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
    return buf.getvalue()


class TestProblemAutoImport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._db_path = os.path.join(self._tmp.name, "test_auto_import.db")
        self._storage_path = os.path.join(self._tmp.name, "storage")
        os.makedirs(self._storage_path, exist_ok=True)

        self._env_patch = patch.dict(
            os.environ,
            {
                "DATABASE_URL": f"sqlite:///{self._db_path}",
                "STORAGE_BACKEND": "local",
                "STORAGE_LOCAL_PATH": self._storage_path,
                "JUDGE_DISPATCH_MODE": "inline",
                "APP_ENV": "test",
                "SECRET_KEY": "test-secret-auto-import",
                "GEMINI_API_KEY": "fake-gemini-key-for-tests",
                "OPENAI_API_KEY": "",
            },
        )
        self._env_patch.start()

        from backend.app.core import database, storage
        from backend.app.core.cache import app_cache
        from backend.app.core.config import get_settings
        from backend.app.main import create_app

        app_cache.clear()
        get_settings.cache_clear()
        database._db_instance = None
        storage._storage_instance = None

        self.db = database.get_db()
        self.db.init_schema()
        for rname in ("admin", "teacher", "student"):
            self.db.execute("INSERT OR IGNORE INTO roles (name) VALUES (%s)", (rname,))

        self.client = TestClient(create_app())
        self.admin_token = self._create_user("admin_ai", "admin_ai@test.local", ["admin"])
        self.student_token = self._create_user("student_ai", "stu_ai@test.local", ["student"])

    def tearDown(self) -> None:
        from backend.app.core import database, storage
        from backend.app.core.cache import app_cache
        from backend.app.core.config import get_settings

        app_cache.clear()
        get_settings.cache_clear()
        database._db_instance = None
        storage._storage_instance = None
        self._env_patch.stop()
        self._tmp.cleanup()

    def _create_user(self, username: str, email: str, roles: List[str]) -> str:
        from backend.app.core.security import create_access_token, hash_password

        uid = self.db.insert_returning_id(
            "INSERT INTO users (username, email, full_name, password_hash, is_active) VALUES (%s, %s, %s, %s, %s)",
            (username, email, username, hash_password("Secret123!"), True),
        )
        for rname in roles:
            role = self.db.fetchone("SELECT id FROM roles WHERE name = %s", (rname,))
            self.db.execute("INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)", (uid, int(role["id"])))
        return create_access_token({"sub": str(uid), "username": username, "roles": roles})

    def _headers(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def test_docx_omml_math_and_table_extraction_in_ram(self) -> None:
        raw = _build_minimal_docx_with_omml_and_table()
        extracted = extract_docx_content_in_memory(raw)
        self.assertIn("\\frac{a}{b}", extracted)
        self.assertIn("a_{i}", extracted)
        self.assertIn("10^{9}", extracted)
        self.assertIn("Sample Input", extracted)
        self.assertIn("1 2 3", extracted)
        self.assertIn("6", extracted)

    def test_validation_rbac_missing_key_and_size_limit(self) -> None:
        # Student forbidden
        r_stu = self.client.post(
            "/api/v1/problems/auto-import",
            headers=self._headers(self.student_token),
            files={"file": ("de.png", VALID_PNG, "image/png")},
        )
        self.assertEqual(r_stu.status_code, 403)

        # Legacy .doc rejected cleanly
        r_doc = self.client.post(
            "/api/v1/problems/auto-import",
            headers=self._headers(self.admin_token),
            files={"file": ("de_cu.doc", b"\xd0\xcf\x11\xe0dummy", "application/msword")},
        )
        self.assertEqual(r_doc.status_code, 400)
        self.assertIn(".docx", r_doc.json()["detail"])

        # Oversized (> 10MB) rejected with 413
        big = VALID_PNG + b"\x00" * (MAX_AUTO_IMPORT_BYTES + 10)
        r_big = self.client.post(
            "/api/v1/problems/auto-import",
            headers=self._headers(self.admin_token),
            files={"file": ("huge.png", big, "image/png")},
        )
        self.assertEqual(r_big.status_code, 413)

        # Missing both API keys returns 503 with Vietnamese guidance
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""}):
            r_nokey = self.client.post(
                "/api/v1/problems/auto-import",
                headers=self._headers(self.admin_token),
                files={"file": ("de.png", VALID_PNG, "image/png")},
            )
            self.assertEqual(r_nokey.status_code, 503)
            self.assertIn("GEMINI_API_KEY", r_nokey.json()["detail"])

    def test_auto_import_image_pdf_docx_and_zero_storage_footprint(self) -> None:
        ai_payload = {
            "title": "Tổng dãy số",
            "description": "Cho dãy $N$ số nguyên $a_1, a_2, \\dots, a_N$. Tính tổng.",
            "input_description": "Dòng 1 chứa $N$. Dòng 2 chứa $N$ số nguyên.",
            "output_description": "In ra tổng các phần tử.",
            "constraints": "$1 \\le N \\le 10^5$, $|a_i| \\le 10^9$.",
            "sample_input": "```\n3\n1 2 3\n```",
            "sample_output": "6",
            "explanation": "Ta có $1 + 2 + 3 = 6$.",
            "time_limit_ms": 2000,
            "memory_limit_mb": 512,
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": json.dumps(ai_payload, ensure_ascii=False)}]}}]
        }

        posted_calls = []

        async def fake_post(url, headers=None, json=None):
            posted_calls.append({"url": url, "headers": headers, "json": json})
            return mock_resp

        with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=fake_post)):
            # 1. PNG image
            r_img = self.client.post(
                "/api/v1/problems/auto-import",
                headers=self._headers(self.admin_token),
                files={"file": ("screenshot.png", VALID_PNG, "image/png")},
            )
            self.assertEqual(r_img.status_code, 200, r_img.text)
            body = r_img.json()
            self.assertEqual(body["title"], "Tổng dãy số")
            self.assertEqual(body["sample_input"], "3\n1 2 3")  # code fences stripped!
            self.assertEqual(body["sample_output"], "6")
            self.assertEqual(body["time_limit_ms"], 2000)
            self.assertEqual(body["memory_limit_mb"], 512)
            # Verify inlineData image/png sent to Gemini with x-goog-api-key header
            self.assertEqual(posted_calls[-1]["headers"]["x-goog-api-key"], "fake-gemini-key-for-tests")
            self.assertEqual(posted_calls[-1]["json"]["contents"][0]["parts"][0]["inlineData"]["mimeType"], "image/png")

            # 2. PDF
            r_pdf = self.client.post(
                "/api/v1/problems/auto-import",
                headers=self._headers(self.admin_token),
                files={"file": ("exam.pdf", VALID_PDF, "application/pdf")},
            )
            self.assertEqual(r_pdf.status_code, 200, r_pdf.text)
            self.assertEqual(posted_calls[-1]["json"]["contents"][0]["parts"][0]["inlineData"]["mimeType"], "application/pdf")

            # 3. DOCX
            docx_bytes = _build_minimal_docx_with_omml_and_table()
            r_docx = self.client.post(
                "/api/v1/problems/auto-import",
                headers=self._headers(self.admin_token),
                files={
                    "file": (
                        "de_hsg.docx",
                        docx_bytes,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
                },
            )
            self.assertEqual(r_docx.status_code, 200, r_docx.text)
            sent_text = posted_calls[-1]["json"]["contents"][0]["parts"][0]["text"]
            self.assertIn("\\frac{a}{b}", sent_text)
            self.assertIn("1 2 3", sent_text)

        # Verify ZERO files were persisted to storage directory (Zero Disk / Zero R2 footprint)
        self.assertEqual(os.listdir(self._storage_path), [])

    def test_openai_fallback_when_gemini_rate_limited(self) -> None:
        gemini_429 = MagicMock()
        gemini_429.status_code = 429

        openai_200 = MagicMock()
        openai_200.status_code = 200
        openai_200.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Fallback OK",
                                "description": "Mô tả",
                                "input_description": "In",
                                "output_description": "Out",
                                "constraints": "$N \\le 100$",
                                "sample_input": "5",
                                "sample_output": "10",
                                "explanation": "",
                                "time_limit_ms": 1000,
                                "memory_limit_mb": 256,
                            }
                        )
                    }
                }
            ]
        }

        async def fake_post(url, headers=None, json=None):
            if "generativelanguage.googleapis.com" in url:
                return gemini_429
            return openai_200

        with patch.dict(os.environ, {"OPENAI_API_KEY": "fake-openai-key"}):
            with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=fake_post)):
                r = self.client.post(
                    "/api/v1/problems/auto-import",
                    headers=self._headers(self.admin_token),
                    files={"file": ("de.png", VALID_PNG, "image/png")},
                )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["title"], "Fallback OK")


if __name__ == "__main__":
    unittest.main()
