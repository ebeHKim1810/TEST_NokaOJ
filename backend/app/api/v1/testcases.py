"""Testcase Management API (/api/v1/testcases) - Strictly restricted to Admin & Teacher."""
import io
import os
import zipfile
from typing import Dict, List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse

from backend.app.core.audit import record_audit_log
from backend.app.core.config import get_settings
from backend.app.core.database import Database, get_db
from backend.app.core.security import get_client_ip, is_admin, require_roles
from backend.app.core.storage import BaseStorage, get_storage
from backend.app.schemas.schemas import (
    TestcaseCreateRequest,
    TestcaseGroupCreate,
    TestcaseSaveAllRequest,
    TestcaseUpdateRequest,
)

router = APIRouter(prefix="/testcases", tags=["Testcases"])


def _verify_problem_access(db: Database, user: dict, problem_id: int) -> dict:
    prob = db.fetchone("SELECT * FROM problems WHERE id = %s AND deleted_at IS NULL", (problem_id,))
    if not prob:
        raise HTTPException(status_code=404, detail="Problem not found.")
    if not is_admin(user) and prob.get("created_by") != user["id"]:
        raise HTTPException(status_code=403, detail="You can only manage testcases for your own problems.")
    return prob


@router.get("/problem/{problem_id}")
def list_testcases(
    problem_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    _verify_problem_access(db, current_user, problem_id)
    groups = db.fetchall(
        "SELECT * FROM testcase_groups WHERE problem_id = %s ORDER BY order_index ASC, id ASC",
        (problem_id,),
    )
    rows = db.fetchall(
        "SELECT * FROM testcases WHERE problem_id = %s ORDER BY order_index ASC, id ASC",
        (problem_id,),
    )
    items = []
    for r in rows:
        in_txt = storage.get_text(r["input_storage_key"])
        out_txt = storage.get_text(r["output_storage_key"])
        items.append(
            {
                **r,
                "input_preview": in_txt[:500],
                "output_preview": out_txt[:500],
                "input_data": in_txt if len(in_txt) <= 20000 else in_txt[:20000],
                "expected_output": out_txt if len(out_txt) <= 20000 else out_txt[:20000],
            }
        )
    return {"groups": groups, "items": items, "total": len(items)}


@router.post("/problem/{problem_id}/groups", status_code=status.HTTP_201_CREATED)
def create_testcase_group(
    problem_id: int,
    payload: TestcaseGroupCreate,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _verify_problem_access(db, current_user, problem_id)
    gid = db.insert_returning_id(
        """
        INSERT INTO testcase_groups (problem_id, name, points, order_index)
        VALUES (%s, %s, %s, %s)
        """,
        (problem_id, payload.name, payload.points, payload.order_index),
    )
    return db.fetchone("SELECT * FROM testcase_groups WHERE id = %s", (gid,))


@router.post("/problem/{problem_id}", status_code=status.HTTP_201_CREATED)
def create_testcase(
    problem_id: int,
    payload: TestcaseCreateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    _verify_problem_access(db, current_user, problem_id)
    cnt = db.fetchone("SELECT COUNT(*) AS cnt FROM testcases WHERE problem_id = %s", (problem_id,))
    order_idx = payload.order_index if payload.order_index > 0 else (int(cnt["cnt"]) + 1 if cnt else 1)

    in_bytes = payload.input_data.encode("utf-8")
    out_bytes = payload.expected_output.encode("utf-8")
    tc_id = db.insert_returning_id(
        """
        INSERT INTO testcases (
            problem_id, group_id, name, input_storage_key, output_storage_key,
            input_size_bytes, output_size_bytes, is_sample, is_hidden, order_index
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            problem_id,
            payload.group_id,
            payload.name,
            "pending",
            "pending",
            len(in_bytes),
            len(out_bytes),
            payload.is_sample,
            False if payload.is_sample else payload.is_hidden,
            order_idx,
        ),
    )
    in_key = f"testcases/p_{problem_id}/tc_{tc_id}.in"
    out_key = f"testcases/p_{problem_id}/tc_{tc_id}.out"
    storage.put_bytes(in_key, in_bytes)
    storage.put_bytes(out_key, out_bytes)
    db.execute(
        "UPDATE testcases SET input_storage_key = %s, output_storage_key = %s WHERE id = %s",
        (in_key, out_key, tc_id),
    )
    record_audit_log(
        db, current_user["id"], "testcase.create", "testcase", str(tc_id), get_client_ip(request)
    )
    return db.fetchone("SELECT * FROM testcases WHERE id = %s", (tc_id,))


@router.post("/problem/{problem_id}/upload-zip")
async def upload_testcases_zip(
    problem_id: int,
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    _verify_problem_access(db, current_user, problem_id)
    if not (file.filename or "").lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip files are allowed.")

    raw = await file.read()
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(raw) > max_bytes:
        raise HTTPException(status_code=413, detail="ZIP archive exceeds maximum allowed size.")

    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid or corrupted ZIP archive.")

    inputs: Dict[str, bytes] = {}
    outputs: Dict[str, bytes] = {}
    warnings: List[str] = []

    for info in zf.infolist():
        if info.is_dir():
            continue
        base = os.path.basename(info.filename)
        if not base or base.startswith(".") or "__MACOSX" in info.filename:
            continue
        stem, ext = os.path.splitext(base)
        ext_low = ext.lower()
        if ext_low in (".in", ".inp"):
            inputs[stem] = zf.read(info)
        elif ext_low in (".out", ".ans"):
            outputs[stem] = zf.read(info)
        else:
            warnings.append(f"Skipped unsupported file: '{base}' (expected .in/.inp and .out/.ans).")

    paired_stems = sorted(set(inputs.keys()) & set(outputs.keys()))
    unpaired_in = sorted(set(inputs.keys()) - set(outputs.keys()))
    unpaired_out = sorted(set(outputs.keys()) - set(inputs.keys()))

    for s in unpaired_in:
        warnings.append(f"Unpaired input file '{s}.in' has no matching output file (.out/.ans).")
    for s in unpaired_out:
        warnings.append(f"Unpaired output file '{s}.out' has no matching input file (.in/.inp).")

    if not paired_stems:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "No valid testcase pairs found in ZIP archive.",
                "warnings": warnings,
            },
        )

    cnt = db.fetchone("SELECT COUNT(*) AS cnt FROM testcases WHERE problem_id = %s", (problem_id,))
    base_order = int(cnt["cnt"]) if cnt else 0
    created = []
    for offset, stem in enumerate(paired_stems, start=1):
        in_b = inputs[stem]
        out_b = outputs[stem]
        tc_id = db.insert_returning_id(
            """
            INSERT INTO testcases (
                problem_id, name, input_storage_key, output_storage_key,
                input_size_bytes, output_size_bytes, is_sample, is_hidden, order_index
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (problem_id, stem, "pending", "pending", len(in_b), len(out_b), False, True, base_order + offset),
        )
        in_key = f"testcases/p_{problem_id}/tc_{tc_id}.in"
        out_key = f"testcases/p_{problem_id}/tc_{tc_id}.out"
        storage.put_bytes(in_key, in_b)
        storage.put_bytes(out_key, out_b)
        db.execute(
            "UPDATE testcases SET input_storage_key = %s, output_storage_key = %s WHERE id = %s",
            (in_key, out_key, tc_id),
        )
        created.append({"id": tc_id, "name": stem, "input_size_bytes": len(in_b), "output_size_bytes": len(out_b)})

    record_audit_log(
        db,
        current_user["id"],
        "testcase.upload_zip",
        "problem",
        str(problem_id),
        get_client_ip(request),
        {"imported": len(created), "warnings": len(warnings)},
    )
    return {
        "imported_count": len(created),
        "created": created,
        "warnings": warnings,
    }


@router.put("/{testcase_id}")
def update_testcase(
    testcase_id: int,
    payload: TestcaseUpdateRequest,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    tc = db.fetchone("SELECT * FROM testcases WHERE id = %s", (testcase_id,))
    if not tc:
        raise HTTPException(status_code=404, detail="Testcase not found.")
    _verify_problem_access(db, current_user, int(tc["problem_id"]))

    if payload.input_data is not None:
        in_b = payload.input_data.encode("utf-8")
        storage.put_bytes(tc["input_storage_key"], in_b)
        db.execute("UPDATE testcases SET input_size_bytes = %s WHERE id = %s", (len(in_b), testcase_id))
    if payload.expected_output is not None:
        out_b = payload.expected_output.encode("utf-8")
        storage.put_bytes(tc["output_storage_key"], out_b)
        db.execute("UPDATE testcases SET output_size_bytes = %s WHERE id = %s", (len(out_b), testcase_id))

    fields = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.group_id is not None:
        fields["group_id"] = payload.group_id
    if payload.is_sample is not None:
        fields["is_sample"] = payload.is_sample
        if payload.is_sample:
            fields["is_hidden"] = False
    if payload.is_hidden is not None:
        fields["is_hidden"] = payload.is_hidden
    if payload.order_index is not None:
        fields["order_index"] = payload.order_index

    if fields:
        sets = ", ".join(f"{k} = %s" for k in fields.keys())
        db.execute(f"UPDATE testcases SET {sets} WHERE id = %s", (*fields.values(), testcase_id))
    return db.fetchone("SELECT * FROM testcases WHERE id = %s", (testcase_id,))


@router.post("/problem/{problem_id}/save-all")
def save_all_testcases(
    problem_id: int,
    payload: TestcaseSaveAllRequest,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    _verify_problem_access(db, current_user, problem_id)
    for item in payload.items:
        db.execute(
            """
            UPDATE testcases
            SET name = COALESCE(%s, name),
                group_id = %s,
                is_sample = COALESCE(%s, is_sample),
                is_hidden = COALESCE(%s, is_hidden),
                order_index = %s
            WHERE id = %s AND problem_id = %s
            """,
            (
                item.name,
                item.group_id,
                item.is_sample,
                item.is_hidden,
                item.order_index,
                item.id,
                problem_id,
            ),
        )
    return {"saved": len(payload.items)}


@router.delete("/{testcase_id}")
def delete_testcase(
    testcase_id: int,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    tc = db.fetchone("SELECT * FROM testcases WHERE id = %s", (testcase_id,))
    if not tc:
        raise HTTPException(status_code=404, detail="Testcase not found.")
    _verify_problem_access(db, current_user, int(tc["problem_id"]))

    storage.delete(tc["input_storage_key"])
    storage.delete(tc["output_storage_key"])
    db.execute("DELETE FROM testcases WHERE id = %s", (testcase_id,))
    record_audit_log(
        db, current_user["id"], "testcase.delete", "testcase", str(testcase_id), get_client_ip(request)
    )
    return {"deleted": True, "id": testcase_id}


@router.get("/problem/{problem_id}/backup")
def backup_testcases_zip(
    problem_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
    storage: BaseStorage = Depends(get_storage),
):
    prob = _verify_problem_access(db, current_user, problem_id)
    rows = db.fetchall(
        "SELECT * FROM testcases WHERE problem_id = %s ORDER BY order_index ASC, id ASC",
        (problem_id,),
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, r in enumerate(rows, start=1):
            stem = r["name"] or f"{idx:02d}"
            zf.writestr(f"{stem}.in", storage.get_bytes(r["input_storage_key"]))
            zf.writestr(f"{stem}.out", storage.get_bytes(r["output_storage_key"]))
    buf.seek(0)
    filename = f"{prob['code']}_testcases.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
