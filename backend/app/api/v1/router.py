"""Main API v1 router aggregating all Noka JUDGE domain routers."""
from fastapi import APIRouter

from backend.app.api.v1 import (
    admin,
    assignments,
    auth,
    classrooms,
    contests,
    problems,
    submissions,
    testcase_generator,
    testcases,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(problems.router)
api_router.include_router(testcases.router)
api_router.include_router(testcase_generator.router)
api_router.include_router(submissions.router)
api_router.include_router(contests.router)
api_router.include_router(classrooms.router)
api_router.include_router(assignments.router)
api_router.include_router(admin.router)
