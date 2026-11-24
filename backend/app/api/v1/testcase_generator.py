"""Advanced Testcase Generator API (/api/v1/testcase-generator)."""
import io
import json
import uuid
import zipfile
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from backend.app.core.audit import record_audit_log
from backend.app.core.database import Database, get_db
from backend.app.core.queue import judge_execution_slot
from backend.app.core.security import get_client_ip, is_admin, require_roles
from backend.app.core.storage import BaseStorage, get_storage
from backend.app.schemas.schemas import GenerateTestcasesRequest, SaveGeneratedBatchRequest
from judge.generators.engine import TestcaseGeneratorEngine
from judge.generators.templates import BUILTIN_TEMPLATES, RANDOMIZATION_PROFILES

router = APIRouter(prefix="/testcase-generator", tags=["Testcase Generator"])


@router.get("/templates")
def list_generator_templates(
    current_user: dict = Depends(require_roles("admin", "teacher")),
):
    return {
        "templates": [
            {"id": tid, **meta} for tid, meta in BUILTIN_TEMPLATES.items()
        ],
        "profiles": RANDOMIZATION_PROFILES,
    }


@router.post("/generate")
def generate_testcases(
    payload: GenerateTestcasesRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    prob = db.fetchone(
        "SELECT id, code, created_by FROM problems WHERE id = %s AND deleted_at IS NULL",
        (payload.problem_id,),
    )
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not is_admin(current_user) and prob.get("created_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Permission denied.")

    engine = TestcaseGeneratorEngine()
    with judge_execution_slot():
        report = engine.generate(
            mode=payload.mode,
            reference_code=payload.reference_code,
            reference_language=payload.reference_language,
            num_tests=payload.num_tests,
            time_limit_ms=payload.time_limit_ms,
            memory_limit_mb=payload.memory_limit_mb,
            seed=payload.seed,
            generator_code=payload.generator_code,
            generator_language=payload.generator_language,
            constraint_schema=payload.constraint_schema,
            template_id=payload.template_id,
            template_params=payload.template_params,
            profile_distribution=payload.profile_distribution,
            allow_empty_output=payload.allow_empty_output,
        )

    batch_id = uuid.uuid4().hex
    report_dict = report.to_dict()
    report_dict["batch_id"] = batch_id
    report_dict["problem_id"] = payload.problem_id
    report_dict["created_by"] = current_user["id"]

    # Persist staging batch in storage for review, ZIP download, and confirmed save
    storage.put_text(
        f"generator_batches/{batch_id}.json",
        json.dumps(report_dict, ensure_ascii=False),
    )

    record_audit_log(
        db,
        current_user["id"],
        "testcase.generate",
        "problem",
        str(payload.problem_id),
        get_client_ip(request),
        {
            "batch_id": batch_id,
            "mode": payload.mode,
            "requested": report.requested_count,
            "success": report.success_count,
            "failed": report.failed_count,
        },
    )

    # Return full preview metadata
    preview_items = []
    for item in report_dict["items"]:
        preview_items.append(
            {
                "index": item["index"],
                "name": item["name"],
                "profile": item["profile"],
                "status": item["status"],
                "input_preview": item["input_data"][:1200],
                "output_preview": item["expected_output"][:1200],
                "input_size_bytes": item["input_size_bytes"],
                "output_size_bytes": item["output_size_bytes"],
                "execution_time_ms": item["execution_time_ms"],
                "memory_kb": item["memory_kb"],
                "error": item["error"],
            }
        )

    return {
        "batch_id": batch_id,
        "problem_id": payload.problem_id,
        "mode": report.mode,
        "requested_count": report.requested_count,
        "success_count": report.success_count,
        "failed_count": report.failed_count,
        "duration_ms": report.duration_ms,
        "seed": report.seed,
        "reference_compile_error": report.reference_compile_error,
        "generator_compile_error": report.generator_compile_error,
        "items": preview_items,
    }


def _load_batch(storage: BaseStorage, batch_id: str) -> Dict[str, Any]:
    raw = storage.get_text(f"generator_batches/{batch_id}.json")
    if not raw:
        raise HTTPException(status_code=404, detail="Generated testcase batch not found or expired.")
    return json.loads(raw)


@router.post("/batches/{batch_id}/save")
def save_generated_batch_to_problem(
    batch_id: str,
    payload: SaveGeneratedBatchRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    if not payload.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Explicit confirmation (confirmed=true) is required before saving generated testcases.",
        )

    batch = _load_batch(storage, batch_id)
    if int(batch["problem_id"]) != payload.problem_id:
        raise HTTPException(status_code=400, detail="Batch does not belong to the target problem.")

    prob = db.fetchone("SELECT id, created_by FROM problems WHERE id = %s AND deleted_at IS NULL", (payload.problem_id,))
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not is_admin(current_user) and prob.get("created_by") != current_user["id"]:
        raise HTTPException(status_code=403, detail="Permission denied.")

    # Never overwrite existing testcases; append cleanly after current highest order_index
    cnt_row = db.fetchone("SELECT COUNT(*) AS cnt FROM testcases WHERE problem_id = %s", (payload.problem_id,))
    base_idx = int(cnt_row["cnt"]) if cnt_row else 0

    selected_set = set(payload.selected_indices)
    saved = []
    for item in batch.get("items", []):
        if item["index"] not in selected_set or item["status"] != "SUCCESS":
            continue
        base_idx += 1
        in_b = item["input_data"].encode("utf-8")
        out_b = item["expected_output"].encode("utf-8")
        name = f"gen_{base_idx:02d}"
        tc_id = db.insert_returning_id(
            """
            INSERT INTO testcases (
                problem_id, group_id, name, input_storage_key, output_storage_key,
                input_size_bytes, output_size_bytes, is_sample, is_hidden, order_index
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                payload.problem_id,
                payload.group_id,
                name,
                "pending",
                "pending",
                len(in_b),
                len(out_b),
                False,
                payload.is_hidden,
                base_idx,
            ),
        )
        in_key = f"testcases/p_{payload.problem_id}/tc_{tc_id}.in"
        out_key = f"testcases/p_{payload.problem_id}/tc_{tc_id}.out"
        storage.put_bytes(in_key, in_b)
        storage.put_bytes(out_key, out_b)
        db.execute(
            "UPDATE testcases SET input_storage_key = %s, output_storage_key = %s WHERE id = %s",
            (in_key, out_key, tc_id),
        )
        saved.append({"id": tc_id, "name": name, "source_index": item["index"]})

    record_audit_log(
        db,
        current_user["id"],
        "testcase.save_generated",
        "problem",
        str(payload.problem_id),
        get_client_ip(request),
        {"batch_id": batch_id, "saved_count": len(saved)},
    )
    return {"saved_count": len(saved), "saved": saved}


@router.get("/batches/{batch_id}/download")
def download_generated_batch_zip(
    batch_id: str,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    storage: BaseStorage = Depends(get_storage),
):
    batch = _load_batch(storage, batch_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in batch.get("items", []):
            if item["status"] != "SUCCESS":
                continue
            stem = item["name"]
            zf.writestr(f"{stem}.in", item["input_data"].encode("utf-8"))
            zf.writestr(f"{stem}.out", item["expected_output"].encode("utf-8"))
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="generated_{batch_id[:8]}.zip"'},
    )
