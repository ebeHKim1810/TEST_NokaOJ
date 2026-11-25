"""
Zero-Disk / Zero-Storage Problem Auto-Import Service.
Reads uploaded .docx, .pdf, or image files strictly in RAM (BytesIO), extracts Word text/tables/OMML math
when applicable, calls Google Gemini API (gemini-2.5-flash) or optional OpenAI fallback to parse structured
Markdown + LaTeX JSON matching Noka Judge's problem creation form, and releases memory immediately.
"""
import base64
import io
import json
import logging
import os
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

import httpx
from fastapi import HTTPException

logger = logging.getLogger("noka.auto_import")

MAX_AUTO_IMPORT_BYTES = 10 * 1024 * 1024  # 10 MB

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

AUTO_IMPORT_SYSTEM_PROMPT = """Bạn là chuyên gia số hóa đề thi lập trình thi đấu (Online Judge / Tin học HSG) thành cấu trúc JSON chuẩn cho hệ thống Noka Judge.

Yêu cầu bắt buộc:
1. Giữ nguyên ngôn ngữ gốc của đề bài (tiếng Việt hoặc tiếng Anh), KHÔNG tóm tắt làm mất chi tiết bài toán.
2. Chuyển đổi TOÀN BỘ biểu thức toán học, tên biến, chỉ số trên/dưới, bất đẳng thức, tập hợp, phân số, căn bậc hai thành cú pháp LaTeX chuẩn tương thích KaTeX:
   - Dùng `$...$` cho công thức cùng dòng (ví dụ: `$N \\le 10^5$`, `$a_i$`, `$\\frac{a}{b}$`, `$\\sqrt{n}$`).
   - Dùng `$$...$$` cho công thức đứng riêng dòng.
   - Đảm bảo escape dấu gạch chéo ngược đúng chuẩn JSON (`\\\\le`, `\\\\frac`, `\\\\sqrt`, `\\\\dots`).
3. Phân tách chính xác các trường:
   - `title`: Tên bài tập (nếu có trong tài liệu, nếu không thì để chuỗi rỗng `""`).
   - `description`: Nội dung mô tả bài toán (Markdown + LaTeX, bỏ tiêu đề lặp lại, bỏ phần Input/Output/Giới hạn/Ví dụ đã tách riêng).
   - `input_description`: Mô tả dữ liệu vào (Markdown + LaTeX).
   - `output_description`: Mô tả dữ liệu ra (Markdown + LaTeX).
   - `constraints`: Giới hạn / Ràng buộc / Subtask (Markdown + LaTeX). Nếu đề gộp giới hạn chung vào mục Input thì tách phần giới hạn/subtask sang trường này.
   - `sample_input`: Dữ liệu vào của Ví dụ 1. Giữ nguyên ĐÚNG ký tự xuống dòng và khoảng trắng, KHÔNG bọc trong dấu ``` hay ghi nhãn "Input:".
   - `sample_output`: Dữ liệu ra của Ví dụ 1. Giữ nguyên ĐÚNG ký tự xuống dòng và khoảng trắng, KHÔNG bọc trong dấu ``` hay ghi nhãn "Output:".
   - `explanation`: Phần giải thích ví dụ (Markdown + LaTeX). Nếu đề có nhiều ví dụ (Ví dụ 2, Ví dụ 3...), hãy đưa các ví dụ bổ sung đó (dùng code block gọn gàng) cùng toàn bộ phần giải thích vào trường `explanation`. Nếu đề không có giải thích và chỉ có 1 ví dụ, để chuỗi rỗng `""`.
   - `time_limit_ms`: Giới hạn thời gian tính bằng mili-giây (số nguyên, ví dụ 1 giây -> 1000, 2.5s -> 2500; mặc định 1000 nếu không nêu).
   - `memory_limit_mb`: Giới hạn bộ nhớ tính bằng MB (số nguyên, ví dụ 256 MB -> 256, 512 MB -> 512; mặc định 256 nếu không nêu).
4. CHỈ trả về duy nhất một JSON object hợp lệ với đúng 10 khóa trên, không kèm bất kỳ văn bản giải thích nào bên ngoài JSON."""

GEMINI_RESPONSE_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
        "input_description": {"type": "STRING"},
        "output_description": {"type": "STRING"},
        "constraints": {"type": "STRING"},
        "sample_input": {"type": "STRING"},
        "sample_output": {"type": "STRING"},
        "explanation": {"type": "STRING"},
        "time_limit_ms": {"type": "INTEGER"},
        "memory_limit_mb": {"type": "INTEGER"},
    },
    "required": [
        "title",
        "description",
        "input_description",
        "output_description",
        "constraints",
        "sample_input",
        "sample_output",
        "explanation",
        "time_limit_ms",
        "memory_limit_mb",
    ],
}


def detect_supported_upload(
    data: bytes, filename: str, content_type: str
) -> Tuple[str, str]:
    """
    Validates uploaded file strictly via magic bytes + extension/MIME.
    Returns (kind, canonical_mime) where kind is one of: 'image', 'pdf', 'docx'.
    """
    ext = os.path.splitext((filename or "").strip().lower())[1]
    mime = (content_type or "").split(";")[0].strip().lower()

    if ext == ".doc" or mime == "application/msword":
        raise HTTPException(
            status_code=400,
            detail="Hệ thống hỗ trợ file Word định dạng .docx (không hỗ trợ .doc cũ). Vui lòng lưu lại thành .docx hoặc .pdf rồi thử lại.",
        )

    # Check images by magic bytes
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ("image", "image/png")
    if data.startswith(b"\xff\xd8\xff"):
        return ("image", "image/jpeg")
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ("image", "image/webp")

    # Check PDF by magic bytes
    if data.startswith(b"%PDF-"):
        return ("pdf", "application/pdf")

    # Check DOCX (ZIP container containing word/document.xml)
    if data.startswith(b"PK\x03\x04") and (
        ext == ".docx"
        or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or mime in ("application/zip", "application/octet-stream", "")
    ):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                if "word/document.xml" in zf.namelist():
                    return (
                        "docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    )
        except zipfile.BadZipFile:
            pass

    raise HTTPException(
        status_code=400,
        detail="Định dạng file không được hỗ trợ hoặc file bị hỏng. Vui lòng chọn .docx, .pdf hoặc ảnh (.png, .jpg, .jpeg, .webp).",
    )


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _serialize_omml(elem: Any) -> str:
    """Converts Word OMML (<m:oMath>) XML nodes into clean LaTeX-like expressions."""
    tag = _local_tag(elem.tag)

    if tag == "t":
        return elem.text or ""
    if tag == "f":  # Fraction
        num = ""
        den = ""
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "num":
                num = _serialize_omml(child).strip()
            elif ct == "den":
                den = _serialize_omml(child).strip()
        return f"\\frac{{{num}}}{{{den}}}"
    if tag == "sSup":  # Superscript
        base = ""
        sup = ""
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "e":
                base = _serialize_omml(child).strip()
            elif ct == "sup":
                sup = _serialize_omml(child).strip()
        return f"{base}^{{{sup}}}"
    if tag == "sSub":  # Subscript
        base = ""
        sub = ""
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "e":
                base = _serialize_omml(child).strip()
            elif ct == "sub":
                sub = _serialize_omml(child).strip()
        return f"{base}_{{{sub}}}"
    if tag == "sSubSup":  # Subscript + Superscript
        base = sub = sup = ""
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "e":
                base = _serialize_omml(child).strip()
            elif ct == "sub":
                sub = _serialize_omml(child).strip()
            elif ct == "sup":
                sup = _serialize_omml(child).strip()
        return f"{base}_{{{sub}}}^{{{sup}}}"
    if tag == "rad":  # Radical / sqrt
        deg = ""
        body = ""
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "deg":
                deg = _serialize_omml(child).strip()
            elif ct == "e":
                body = _serialize_omml(child).strip()
        return f"\\sqrt[{deg}]{{{body}}}" if deg else f"\\sqrt{{{body}}}"
    if tag == "d":  # Delimiters (parentheses, brackets, abs)
        beg = "("
        end = ")"
        parts: List[str] = []
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "dPr":
                for pr in child:
                    pt = _local_tag(pr.tag)
                    val = pr.attrib.get(f"{{{M_NS}}}val")
                    if pt == "begChr" and val is not None:
                        beg = val
                    elif pt == "endChr" and val is not None:
                        end = val
            elif ct == "e":
                parts.append(_serialize_omml(child).strip())
        return f"{beg}{', '.join(parts)}{end}"
    if tag == "nary":  # Sum / Product / Integral
        op_chr = "\\sum"
        sub = sup = body = ""
        for child in elem:
            ct = _local_tag(child.tag)
            if ct == "naryPr":
                for pr in child:
                    if _local_tag(pr.tag) == "chr":
                        c = pr.attrib.get(f"{{{M_NS}}}val", "")
                        if c == "∏":
                            op_chr = "\\prod"
                        elif c == "∫":
                            op_chr = "\\int"
                        elif c:
                            op_chr = c
            elif ct == "sub":
                sub = _serialize_omml(child).strip()
            elif ct == "sup":
                sup = _serialize_omml(child).strip()
            elif ct == "e":
                body = _serialize_omml(child).strip()
        res = op_chr
        if sub:
            res += f"_{{{sub}}}"
        if sup:
            res += f"^{{{sup}}}"
        if body:
            res += f" {body}"
        return res
    if tag in ("rPr", "ctrlPr", "fPr", "radPr", "sSupPr", "sSubPr", "sSubSupPr"):
        return ""

    return "".join(_serialize_omml(child) for child in elem)


def _serialize_w_paragraph(p_elem: Any) -> str:
    """Extracts text, superscript/subscript runs, line breaks, and OMML math from a <w:p> element."""
    parts: List[str] = []
    for child in p_elem:
        tag = _local_tag(child.tag)
        if tag == "r":
            vert = ""
            rpr = child.find(f"{{{W_NS}}}rPr")
            if rpr is not None:
                va = rpr.find(f"{{{W_NS}}}vertAlign")
                if va is not None:
                    vert = va.attrib.get(f"{{{W_NS}}}val", "")
            run_chunks: List[str] = []
            for rchild in child:
                rt = _local_tag(rchild.tag)
                if rt == "t" and rchild.text:
                    run_chunks.append(rchild.text)
                elif rt == "tab":
                    run_chunks.append("\t")
                elif rt in ("br", "cr"):
                    run_chunks.append("\n")
            txt = "".join(run_chunks)
            if txt:
                if vert == "superscript":
                    parts.append(f"^{{{txt}}}")
                elif vert == "subscript":
                    parts.append(f"_{{{txt}}}")
                else:
                    parts.append(txt)
        elif tag == "oMath":
            math_str = _serialize_omml(child).strip()
            if math_str:
                parts.append(f"${math_str}$")
        elif tag == "oMathPara":
            math_str = _serialize_omml(child).strip()
            if math_str:
                parts.append(f"\n$${math_str}$$\n")
        elif tag == "hyperlink":
            parts.append(_serialize_w_paragraph(child))
    return "".join(parts)


def _serialize_w_table(tbl_elem: Any) -> str:
    """Serializes a Word table preserving multi-line cells (essential for Sample Input/Output tables)."""
    lines: List[str] = ["[BẢNG TRONG TÀI LIỆU WORD]"]
    rows = tbl_elem.findall(f"{{{W_NS}}}tr")
    for r_idx, row in enumerate(rows, start=1):
        cells = row.findall(f"{{{W_NS}}}tc")
        cell_texts: List[str] = []
        for c_idx, cell in enumerate(cells, start=1):
            paras = [_serialize_w_paragraph(p) for p in cell.findall(f"{{{W_NS}}}p")]
            cell_content = "\n".join(paras).strip()
            cell_texts.append(f"--- Cột {c_idx} ---\n{cell_content}")
        lines.append(f"[Hàng {r_idx}]\n" + "\n".join(cell_texts))
    lines.append("[KẾT THÚC BẢNG]")
    return "\n".join(lines)


def extract_docx_content_in_memory(data: bytes) -> str:
    """
    Extracts full paragraphs, OMML mathematical equations, and tables from a .docx binary buffer in RAM
    using python-docx (with pure-stdlib XML fallback). Never touches the filesystem.
    """
    body_elem = None
    try:
        import docx  # type: ignore

        doc = docx.Document(io.BytesIO(data))
        body_elem = doc.element.body
    except ImportError:
        # Fallback if python-docx is unavailable in minimal local test environment
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
        body_elem = root.find(f"{{{W_NS}}}body")
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Không thể đọc nội dung file Word (.docx): {exc}",
        )

    if body_elem is None:
        return ""

    blocks: List[str] = []
    for child in body_elem:
        tag = _local_tag(child.tag)
        if tag == "p":
            txt = _serialize_w_paragraph(child).strip()
            if txt:
                blocks.append(txt)
        elif tag == "tbl":
            blocks.append(_serialize_w_table(child))
    return "\n\n".join(blocks).strip()


def _parse_and_normalize_ai_json(raw_text: str) -> Dict[str, Any]:
    cleaned = (raw_text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Attempt to salvage first JSON object block if wrapped in prose
        m = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not m:
            raise HTTPException(
                status_code=502,
                detail="AI trả về dữ liệu không đúng định dạng JSON. Vui lòng thử lại.",
            )
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=502,
                detail="AI trả về dữ liệu JSON không hợp lệ. Vui lòng thử lại.",
            )

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail="AI trả về cấu trúc dữ liệu không hợp lệ.",
        )

    def _str_field(key: str, preserve_leading: bool = False) -> str:
        val = parsed.get(key)
        if val is None:
            return ""
        s = str(val).replace("\r\n", "\n")
        return s.strip("\n") if preserve_leading else s.strip()

    def _int_clamped(key: str, default: int, lo: int, hi: int) -> int:
        val = parsed.get(key)
        try:
            num = int(round(float(val)))
            return max(lo, min(hi, num))
        except (TypeError, ValueError):
            return default

    # Strip accidental markdown code fences inside sample_input/sample_output
    def _clean_sample(val: str) -> str:
        s = val.strip("\n")
        if s.startswith("```"):
            s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
            s = re.sub(r"\n?```$", "", s)
        return s.strip("\n")

    return {
        "title": _str_field("title"),
        "description": _str_field("description"),
        "input_description": _str_field("input_description"),
        "output_description": _str_field("output_description"),
        "constraints": _str_field("constraints"),
        "sample_input": _clean_sample(_str_field("sample_input", preserve_leading=True)),
        "sample_output": _clean_sample(_str_field("sample_output", preserve_leading=True)),
        "explanation": _str_field("explanation"),
        "time_limit_ms": _int_clamped("time_limit_ms", 1000, 100, 30000),
        "memory_limit_mb": _int_clamped("memory_limit_mb", 256, 16, 2048),
    }


async def _call_gemini_api(
    api_key: str,
    model: str,
    kind: str,
    mime_type: str,
    raw_bytes: bytes,
    docx_text: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts: List[Dict[str, Any]] = []
    if kind == "docx":
        parts.append(
            {
                "text": (
                    "Hãy đọc nội dung đề bài trích xuất từ file Word (.docx) dưới đây, "
                    "chuẩn hóa toàn bộ công thức toán học thành LaTeX và phân tách thành JSON chuẩn:\n\n"
                    f"{docx_text or ''}"
                )
            }
        )
    else:
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        parts.append({"inlineData": {"mimeType": mime_type, "data": b64}})
        parts.append(
            {
                "text": (
                    "Hãy đọc toàn bộ đề bài từ tài liệu/hình ảnh đính kèm, giữ nguyên ngôn ngữ gốc, "
                    "chuyển tất cả công thức toán học sang LaTeX chuẩn và trả về JSON theo đúng cấu trúc yêu cầu."
                )
            }
        )

    payload = {
        "systemInstruction": {"parts": [{"text": AUTO_IMPORT_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
            "responseSchema": GEMINI_RESPONSE_SCHEMA,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            resp = await client.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Hết thời gian chờ phản hồi từ Google Gemini API. Vui lòng thử lại hoặc dùng ảnh/file nhỏ hơn.",
        )
    except httpx.HTTPError as exc:
        logger.warning("Gemini network error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail="Không thể kết nối tới Google Gemini API. Vui lòng kiểm tra kết nối mạng server và thử lại.",
        )

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Google Gemini API đang quá tải hoặc chạm hạn mức miễn phí tạm thời. Vui lòng chờ vài giây rồi thử lại.",
        )
    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail="Khóa GEMINI_API_KEY không hợp lệ hoặc chưa được cấp quyền. Vui lòng kiểm tra lại cấu hình trên Railway.",
        )
    if resp.status_code >= 400:
        err_msg = ""
        try:
            err_msg = resp.json().get("error", {}).get("message", "")
        except Exception:
            err_msg = resp.text[:250]
        logger.warning("Gemini HTTP %s: %s", resp.status_code, err_msg)
        raise HTTPException(
            status_code=502,
            detail=f"Gemini API báo lỗi (HTTP {resp.status_code}): {err_msg or 'Không thể xử lý tài liệu.'}",
        )

    body = resp.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise HTTPException(
            status_code=502,
            detail="Gemini không trả về nội dung nào (có thể ảnh quá mờ hoặc bị bộ lọc an toàn chặn).",
        )
    resp_parts = candidates[0].get("content", {}).get("parts") or []
    text_out = "".join(p.get("text", "") for p in resp_parts if isinstance(p, dict))
    if not text_out.strip():
        raise HTTPException(
            status_code=502,
            detail="Gemini trả về kết quả rỗng. Vui lòng kiểm tra lại file đầu vào.",
        )
    return _parse_and_normalize_ai_json(text_out)


async def _call_openai_api(
    api_key: str,
    model: str,
    kind: str,
    mime_type: str,
    filename: str,
    raw_bytes: bytes,
    docx_text: Optional[str] = None,
) -> Dict[str, Any]:
    url = "https://api.openai.com/v1/chat/completions"
    user_content: Any
    if kind == "docx":
        user_content = (
            "Hãy đọc nội dung đề bài trích xuất từ file Word (.docx) dưới đây, "
            "chuẩn hóa toàn bộ công thức toán học thành LaTeX và phân tách thành JSON chuẩn:\n\n"
            f"{docx_text or ''}"
        )
    elif kind == "image":
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        user_content = [
            {
                "type": "text",
                "text": "Hãy đọc toàn bộ đề bài từ hình ảnh này và trả về JSON theo đúng cấu trúc yêu cầu.",
            },
            {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            },
        ]
    else:
        # PDF via OpenAI Chat Completions file content block
        b64 = base64.b64encode(raw_bytes).decode("ascii")
        user_content = [
            {
                "type": "file",
                "file": {
                    "filename": filename or "problem.pdf",
                    "file_data": f"data:application/pdf;base64,{b64}",
                },
            },
            {
                "type": "text",
                "text": "Hãy đọc toàn bộ đề bài từ file PDF này và trả về JSON theo đúng cấu trúc yêu cầu.",
            },
        ]

    payload = {
        "model": model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": AUTO_IMPORT_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=15.0)) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Hết thời gian chờ phản hồi từ OpenAI API. Vui lòng thử lại.",
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="Không thể kết nối tới OpenAI API. Vui lòng thử lại sau.",
        )

    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="OpenAI API đang quá tải hoặc hết hạn mức. Vui lòng thử lại sau.",
        )
    if resp.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail="Khóa OPENAI_API_KEY không hợp lệ. Vui lòng kiểm tra lại cấu hình.",
        )
    if resp.status_code >= 400:
        err_msg = ""
        try:
            err_msg = resp.json().get("error", {}).get("message", "")
        except Exception:
            err_msg = resp.text[:250]
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI API báo lỗi (HTTP {resp.status_code}): {err_msg or 'Không thể xử lý tài liệu.'}",
        )

    body = resp.json()
    choices = body.get("choices") or []
    content = choices[0].get("message", {}).get("content", "") if choices else ""
    if not content.strip():
        raise HTTPException(status_code=502, detail="OpenAI trả về kết quả rỗng.")
    return _parse_and_normalize_ai_json(content)


async def auto_import_problem_from_bytes(
    data: bytes,
    filename: str,
    content_type: str,
) -> Tuple[Dict[str, Any], str]:
    """
    Validates and parses uploaded problem bytes purely in RAM (Zero Disk / Zero R2).
    Returns (structured_problem_dict, provider_name).
    """
    if not data:
        raise HTTPException(status_code=400, detail="File tải lên bị trống.")
    if len(data) > MAX_AUTO_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File vượt quá dung lượng tối đa 10MB. Vui lòng nén hoặc chọn file nhẹ hơn.",
        )

    kind, canonical_mime = detect_supported_upload(data, filename, content_type)

    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"

    if not gemini_key and not openai_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chưa cấu hình khóa AI (GEMINI_API_KEY) trên server Backend. "
                "Vui lòng thiết lập biến môi trường GEMINI_API_KEY trên Railway để sử dụng tính năng Nhập đề tự động."
            ),
        )

    docx_text: Optional[str] = None
    if kind == "docx":
        docx_text = extract_docx_content_in_memory(data)
        if not docx_text.strip():
            raise HTTPException(
                status_code=400,
                detail="File Word (.docx) không chứa nội dung văn bản nào để trích xuất.",
            )

    if gemini_key:
        try:
            result = await _call_gemini_api(
                api_key=gemini_key,
                model=gemini_model,
                kind=kind,
                mime_type=canonical_mime,
                raw_bytes=data,
                docx_text=docx_text,
            )
            return result, f"gemini:{gemini_model}"
        except HTTPException as exc:
            # Fallback to OpenAI only if explicitly configured and Gemini failed due to quota/upstream error
            if openai_key and exc.status_code in (429, 502, 504):
                logger.warning("Gemini failed (%s), falling back to OpenAI.", exc.status_code)
                result = await _call_openai_api(
                    api_key=openai_key,
                    model=openai_model,
                    kind=kind,
                    mime_type=canonical_mime,
                    filename=filename,
                    raw_bytes=data,
                    docx_text=docx_text,
                )
                return result, f"openai:{openai_model}"
            raise

    result = await _call_openai_api(
        api_key=openai_key,
        model=openai_model,
        kind=kind,
        mime_type=canonical_mime,
        filename=filename,
        raw_bytes=data,
        docx_text=docx_text,
    )
    return result, f"openai:{openai_model}"
