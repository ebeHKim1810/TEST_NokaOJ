"""Assignments API (/api/v1/assignments)."""
from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.core.database import Database, get_db
from backend.app.core.security import get_current_user, require_roles
from backend.app.schemas.schemas import AssignmentCreateRequest

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.post("", status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreateRequest,
    current_user: dict = Depends(require_roles("admin", "teacher")),
    db: Database = Depends(get_db),
):
    cls = db.fetchone(
        "SELECT id FROM classrooms WHERE id = %s AND deleted_at IS NULL", (payload.classroom_id,)
    )
    if not cls:
        raise HTTPException(status_code=404, detail="Classroom not found.")

    aid = db.insert_returning_id(
        """
        INSERT INTO assignments (classroom_id, title, description, due_at, created_by)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (payload.classroom_id, payload.title, payload.description, payload.due_at, current_user["id"]),
    )
    for idx, pid in enumerate(payload.problem_ids):
        prob = db.fetchone("SELECT id, points FROM problems WHERE id = %s", (pid,))
        if prob:
            db.execute(
                """
                INSERT INTO assignment_problems (assignment_id, problem_id, points, order_index)
                VALUES (%s, %s, %s, %s)
                """,
                (aid, pid, prob["points"], idx),
            )
    return db.fetchone("SELECT * FROM assignments WHERE id = %s", (aid,))


@router.get("/my")
def my_assignments(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    rows = db.fetchall(
        """
        SELECT a.*, c.name AS classroom_name
        FROM assignments a
        JOIN classrooms c ON c.id = a.classroom_id
        JOIN classroom_students cs ON cs.classroom_id = c.id
        WHERE cs.student_id = %s AND a.deleted_at IS NULL AND c.deleted_at IS NULL
        ORDER BY a.due_at ASC, a.id DESC
        """,
        (current_user["id"],),
    )
    if rows:
        aids = [int(a["id"]) for a in rows]
        aph = ", ".join(["%s"] * len(aids))
        ap_rows = db.fetchall(
            f"""
            SELECT ap.assignment_id, p.id, p.code, p.title, p.difficulty, ap.points
            FROM assignment_problems ap
            JOIN problems p ON p.id = ap.problem_id
            WHERE ap.assignment_id IN ({aph})
            ORDER BY ap.order_index ASC
            """,
            tuple(aids),
        )
        ap_map: dict[int, list[dict]] = {}
        for ap in ap_rows:
            aid = int(ap.pop("assignment_id"))
            ap_map.setdefault(aid, []).append(ap)
        for a in rows:
            a["problems"] = ap_map.get(int(a["id"]), [])
    return {"items": rows}
