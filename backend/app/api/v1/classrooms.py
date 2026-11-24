"""Classroom Management API (/api/v1/classrooms) including CSV/Excel student import and progress tracking."""
import csv
import io
import secrets
import string
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from backend.app.core.audit import record_audit_log
from backend.app.core.database import Database, get_db
from backend.app.core.security import (
    get_client_ip,
    get_current_user,
    hash_password,
    is_admin,
    is_staff,
    require_roles,
)
from backend.app.schemas.schemas import (
    AddStudentRequest,
    ClassroomCreateRequest,
    JoinClassroomRequest,
)

router = APIRouter(prefix="/classrooms", tags=["Classrooms"])


def _gen_join_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


@router.get("")
def list_classrooms(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    if is_admin(current_user):
        rows = db.fetchall(
            """
            SELECT c.*, u.username AS teacher_username, u.full_name AS teacher_name
            FROM classrooms c
            LEFT JOIN users u ON u.id = c.teacher_id
            WHERE c.deleted_at IS NULL
            ORDER BY c.id DESC
            """
        )
    elif "teacher" in current_user.get("roles", []):
        rows = db.fetchall(
            """
            SELECT c.*, u.username AS teacher_username, u.full_name AS teacher_name
            FROM classrooms c
            LEFT JOIN users u ON u.id = c.teacher_id
            WHERE c.deleted_at IS NULL AND c.teacher_id = %s
            ORDER BY c.id DESC
            """,
            (current_user["id"],),
        )
    else:
        rows = db.fetchall(
            """
            SELECT c.*, u.username AS teacher_username, u.full_name AS teacher_name
            FROM classrooms c
            JOIN classroom_students cs ON cs.classroom_id = c.id
            LEFT JOIN users u ON u.id = c.teacher_id
            WHERE c.deleted_at IS NULL AND cs.student_id = %s
            ORDER BY c.id DESC
            """,
            (current_user["id"],),
        )

    for r in rows:
        sc = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM classroom_students WHERE classroom_id = %s", (r["id"],)
        )
        ac = db.fetchone(
            "SELECT COUNT(*) AS cnt FROM assignments WHERE classroom_id = %s AND deleted_at IS NULL",
            (r["id"],),
        )
        r["student_count"] = int(sc["cnt"]) if sc else 0
        r["assignment_count"] = int(ac["cnt"]) if ac else 0
    return {"items": rows}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_classroom(
    payload: ClassroomCreateRequest,
    request: Request,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    code = _gen_join_code()
    cid = db.insert_returning_id(
        """
        INSERT INTO classrooms (name, description, join_code, teacher_id, is_active)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (payload.name, payload.description, code, current_user["id"], True),
    )
    record_audit_log(
        db, current_user["id"], "classroom.create", "classroom", str(cid), get_client_ip(request)
    )
    return db.fetchone("SELECT * FROM classrooms WHERE id = %s", (cid,))


@router.post("/join")
def join_classroom(
    payload: JoinClassroomRequest,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    cls = db.fetchone(
        "SELECT * FROM classrooms WHERE join_code = %s AND deleted_at IS NULL",
        (payload.join_code.strip().upper(),),
    )
    if not cls:
        raise HTTPException(status_code=404, detail="Invalid classroom join code.")
    exists = db.fetchone(
        "SELECT 1 FROM classroom_students WHERE classroom_id = %s AND student_id = %s",
        (cls["id"], current_user["id"]),
    )
    if not exists:
        db.execute(
            "INSERT INTO classroom_students (classroom_id, student_id) VALUES (%s, %s)",
            (cls["id"], current_user["id"]),
        )
    return {"joined": True, "classroom": cls}


@router.get("/{classroom_id}")
def get_classroom_detail(
    classroom_id: int,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    cls = db.fetchone("SELECT * FROM classrooms WHERE id = %s AND deleted_at IS NULL", (classroom_id,))
    if not cls:
        raise HTTPException(status_code=404, detail="Classroom not found.")

    if not is_staff(current_user):
        member = db.fetchone(
            "SELECT 1 FROM classroom_students WHERE classroom_id = %s AND student_id = %s",
            (classroom_id, current_user["id"]),
        )
        if not member:
            raise HTTPException(status_code=403, detail="You are not enrolled in this classroom.")

    assignments = db.fetchall(
        """
        SELECT * FROM assignments
        WHERE classroom_id = %s AND deleted_at IS NULL
        ORDER BY id DESC
        """,
        (classroom_id,),
    )
    for a in assignments:
        a["problems"] = db.fetchall(
            """
            SELECT p.id, p.code, p.title, p.difficulty, ap.points
            FROM assignment_problems ap
            JOIN problems p ON p.id = ap.problem_id
            WHERE ap.assignment_id = %s
            ORDER BY ap.order_index ASC
            """,
            (a["id"],),
        )

    students = []
    if is_staff(current_user):
        students = db.fetchall(
            """
            SELECT u.id, u.username, u.email, u.full_name, cs.joined_at
            FROM classroom_students cs
            JOIN users u ON u.id = cs.student_id
            WHERE cs.classroom_id = %s
            ORDER BY u.full_name ASC, u.username ASC
            """,
            (classroom_id,),
        )

    cls["assignments"] = assignments
    cls["students"] = students
    return cls


@router.post("/{classroom_id}/students")
def add_student(
    classroom_id: int,
    payload: AddStudentRequest,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    cls = db.fetchone("SELECT * FROM classrooms WHERE id = %s AND deleted_at IS NULL", (classroom_id,))
    if not cls:
        raise HTTPException(status_code=404, detail="Classroom not found.")
    user = db.fetchone(
        "SELECT id, username, email, full_name FROM users WHERE (username = %s OR email = %s) AND deleted_at IS NULL",
        (payload.username_or_email, payload.username_or_email),
    )
    if not user:
        raise HTTPException(status_code=404, detail="Student account not found.")
    exists = db.fetchone(
        "SELECT 1 FROM classroom_students WHERE classroom_id = %s AND student_id = %s",
        (classroom_id, user["id"]),
    )
    if not exists:
        db.execute(
            "INSERT INTO classroom_students (classroom_id, student_id) VALUES (%s, %s)",
            (classroom_id, user["id"]),
        )
    return {"added": True, "student": user}


@router.post("/{classroom_id}/students/import")
async def import_students_csv_or_excel(
    classroom_id: int,
    file: UploadFile = File(...),
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    """Import students into classroom from CSV or Excel (.xlsx) with columns: username, email, full_name, password."""
    cls = db.fetchone("SELECT * FROM classrooms WHERE id = %s AND deleted_at IS NULL", (classroom_id,))
    if not cls:
        raise HTTPException(status_code=404, detail="Classroom not found.")

    raw = await file.read()
    fname = (file.filename or "").lower()
    rows_data: List[dict] = []

    if fname.endswith(".xlsx"):
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True)
        ws = wb.active
        headers = [str(c.value or "").strip().lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            rows_data.append({headers[i]: str(row[i] or "").strip() for i in range(min(len(headers), len(row)))})
    elif fname.endswith(".csv"):
        reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig", errors="replace")))
        for row in reader:
            rows_data.append({(k or "").strip().lower(): (v or "").strip() for k, v in row.items()})
    else:
        raise HTTPException(status_code=400, detail="Only .csv and .xlsx files are supported.")

    student_role = db.fetchone("SELECT id FROM roles WHERE name = 'student'")
    added = 0
    created_accounts = 0
    errors = []

    for idx, item in enumerate(rows_data, start=2):
        uname = item.get("username", "")
        email = item.get("email", "")
        full_name = item.get("full_name", uname)
        pwd = item.get("password", "") or secrets.token_urlsafe(10)
        if not uname:
            errors.append(f"Row {idx}: missing username.")
            continue
        user = db.fetchone(
            "SELECT id FROM users WHERE username = %s OR (email = %s AND email != '')",
            (uname, email),
        )
        if user:
            uid = int(user["id"])
        else:
            if not email:
                email = f"{uname}@student.local"
            uid = db.insert_returning_id(
                """
                INSERT INTO users (username, email, full_name, password_hash, is_active)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (uname, email, full_name, hash_password(pwd), True),
            )
            if student_role:
                db.execute(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (%s, %s)",
                    (uid, student_role["id"]),
                )
            created_accounts += 1

        if not db.fetchone(
            "SELECT 1 FROM classroom_students WHERE classroom_id = %s AND student_id = %s",
            (classroom_id, uid),
        ):
            db.execute(
                "INSERT INTO classroom_students (classroom_id, student_id) VALUES (%s, %s)",
                (classroom_id, uid),
            )
            added += 1

    return {"enrolled_count": added, "created_accounts": created_accounts, "errors": errors}


@router.get("/{classroom_id}/progress")
def get_classroom_progress(
    classroom_id: int,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    cls = db.fetchone("SELECT * FROM classrooms WHERE id = %s AND deleted_at IS NULL", (classroom_id,))
    if not cls:
        raise HTTPException(status_code=404, detail="Classroom not found.")

    assigned_problems = db.fetchall(
        """
        SELECT DISTINCT p.id, p.code, p.title, p.points
        FROM assignment_problems ap
        JOIN assignments a ON a.id = ap.assignment_id
        JOIN problems p ON p.id = ap.problem_id
        WHERE a.classroom_id = %s AND a.deleted_at IS NULL
        """,
        (classroom_id,),
    )
    prob_ids = [int(p["id"]) for p in assigned_problems]
    students = db.fetchall(
        """
        SELECT u.id, u.username, u.full_name
        FROM classroom_students cs
        JOIN users u ON u.id = cs.student_id
        WHERE cs.classroom_id = %s
        ORDER BY u.full_name ASC, u.username ASC
        """,
        (classroom_id,),
    )

    progress = []
    for st in students:
        sid = int(st["id"])
        solved_ids = set()
        total_score = 0
        for pid in prob_ids:
            best = db.fetchone(
                """
                SELECT MAX(score) AS best_score,
                       MAX(CASE WHEN verdict = 'AC' THEN 1 ELSE 0 END) AS is_ac
                FROM submissions
                WHERE user_id = %s AND problem_id = %s
                """,
                (sid, pid),
            )
            if best and best["best_score"] is not None:
                total_score += int(best["best_score"])
            if best and best["is_ac"]:
                solved_ids.add(pid)

        sub_cnt = db.fetchone("SELECT COUNT(*) AS cnt FROM submissions WHERE user_id = %s", (sid,))
        progress.append(
            {
                "student_id": sid,
                "username": st["username"],
                "full_name": st["full_name"],
                "ac_count": len(solved_ids),
                "unsolved_count": max(0, len(prob_ids) - len(solved_ids)),
                "total_assigned": len(prob_ids),
                "total_score": total_score,
                "submission_count": int(sub_cnt["cnt"]) if sub_cnt else 0,
            }
        )

    return {"classroom_id": classroom_id, "assigned_problems": assigned_problems, "students": progress}
