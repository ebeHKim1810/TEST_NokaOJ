"""Pydantic v2 request and response schemas for all Noka JUDGE API modules."""
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# --- Auth & Users ---
class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field("", max_length=128)
    password: str = Field(..., min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., min_length=5, max_length=255)
    full_name: str = Field("", max_length=128)
    password: str = Field(..., min_length=6, max_length=128)
    roles: List[Literal["admin", "teacher", "student"]] = Field(default_factory=lambda: ["student"])


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, max_length=128)
    is_active: Optional[bool] = None
    roles: Optional[List[Literal["admin", "teacher", "student"]]] = None


# --- Problems ---
class ProblemSampleItem(BaseModel):
    input: str = Field("", max_length=50000)
    output: str = Field("", max_length=50000)
    explanation: str = Field("", max_length=100000)


class ProblemCreateRequest(BaseModel):
    code: Optional[str] = Field(None, max_length=32)
    title: str = Field(..., min_length=2, max_length=255)
    statement_md: str = Field("", max_length=100000)
    input_description: str = Field("", max_length=50000)
    output_description: str = Field("", max_length=50000)
    constraints_md: str = Field("", max_length=50000)
    sample_input: str = Field("", max_length=50000)
    sample_output: str = Field("", max_length=50000)
    explanation: Optional[str] = Field(None, max_length=100000)
    samples: Optional[List[ProblemSampleItem]] = None
    time_limit_ms: int = Field(1000, ge=100, le=30000)
    memory_limit_mb: int = Field(256, ge=16, le=2048)
    points: int = Field(100, ge=1, le=10000)
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    visibility: Literal["public", "private", "hidden", "classroom"] = "public"
    submission_retention_mode: Literal["latest", "best"] = "latest"
    allowed_user_ids: List[int] = Field(default_factory=list)
    checker_type: Literal["standard", "strict", "float_tol", "custom"] = "standard"
    checker_language: Literal["python3", "cpp17", "cpp20"] = "python3"
    checker_source: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class ProblemUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=255)
    statement_md: Optional[str] = None
    input_description: Optional[str] = None
    output_description: Optional[str] = None
    constraints_md: Optional[str] = None
    sample_input: Optional[str] = None
    sample_output: Optional[str] = None
    explanation: Optional[str] = Field(None, max_length=100000)
    samples: Optional[List[ProblemSampleItem]] = None
    time_limit_ms: Optional[int] = Field(None, ge=100, le=30000)
    memory_limit_mb: Optional[int] = Field(None, ge=16, le=2048)
    points: Optional[int] = Field(None, ge=1, le=10000)
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None
    visibility: Optional[Literal["public", "private", "hidden", "classroom"]] = None
    submission_retention_mode: Optional[Literal["latest", "best"]] = None
    allowed_user_ids: Optional[List[int]] = None
    checker_type: Optional[Literal["standard", "strict", "float_tol", "custom"]] = None
    checker_language: Optional[Literal["python3", "cpp17", "cpp20"]] = None
    checker_source: Optional[str] = None
    tags: Optional[List[str]] = None


class ProblemAccessUpdateRequest(BaseModel):
    visibility: Optional[Literal["public", "private", "hidden", "classroom"]] = None
    allowed_user_ids: Optional[List[int]] = None
    submission_retention_mode: Optional[Literal["latest", "best"]] = None


# --- Testcases ---
class TestcaseGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    points: int = Field(100, ge=0, le=10000)
    order_index: int = Field(0, ge=0)


class TestcaseCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    input_data: str = ""
    expected_output: str = ""
    group_id: Optional[int] = None
    is_sample: bool = False
    is_hidden: bool = True
    order_index: int = 0


class TestcaseUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=64)
    input_data: Optional[str] = None
    expected_output: Optional[str] = None
    group_id: Optional[int] = None
    is_sample: Optional[bool] = None
    is_hidden: Optional[bool] = None
    order_index: Optional[int] = None


class TestcaseBatchSaveItem(BaseModel):
    id: int
    name: Optional[str] = None
    group_id: Optional[int] = None
    is_sample: Optional[bool] = None
    is_hidden: Optional[bool] = None
    order_index: int


class TestcaseSaveAllRequest(BaseModel):
    items: List[TestcaseBatchSaveItem]


# --- Advanced Testcase Generator ---
class GenerateTestcasesRequest(BaseModel):
    problem_id: int
    mode: Literal["custom_generator", "constraints", "builtin_template"]
    reference_code: str = Field(..., min_length=1)
    reference_language: Literal["cpp17", "cpp20", "python3"]
    num_tests: int = Field(10, ge=1, le=100)
    time_limit_ms: int = Field(2000, ge=100, le=15000)
    memory_limit_mb: int = Field(256, ge=32, le=1024)
    seed: Optional[int] = None
    generator_code: Optional[str] = None
    generator_language: Optional[Literal["cpp17", "cpp20", "python3"]] = None
    constraint_schema: Optional[Dict[str, Any]] = None
    template_id: Optional[str] = None
    template_params: Optional[Dict[str, Any]] = None
    profile_distribution: Optional[Dict[str, int]] = None
    allow_empty_output: bool = False


class SaveGeneratedBatchRequest(BaseModel):
    problem_id: int
    selected_indices: List[int]
    group_id: Optional[int] = None
    is_hidden: bool = True
    confirmed: bool = False


# --- Submissions ---
class SubmissionCreateRequest(BaseModel):
    problem_id: int
    language: Literal["cpp17", "cpp20", "python3"]
    source_code: str = Field(..., min_length=1, max_length=200000)
    contest_id: Optional[int] = None


class RunSampleRequest(BaseModel):
    problem_id: int
    language: Literal["cpp17", "cpp20", "python3"]
    source_code: str = Field(..., min_length=1, max_length=200000)
    custom_input: Optional[str] = None


# --- Contests ---
class ContestProblemInput(BaseModel):
    problem_id: int
    label: str = Field("A", max_length=8)
    points: int = Field(100, ge=1)


class ContestCreateRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    start_time: str
    end_time: str
    visibility: Literal["public", "private", "classroom"] = "public"
    classroom_id: Optional[int] = None
    penalty_minutes: int = Field(20, ge=0, le=120)
    freeze_before_end_minutes: int = Field(0, ge=0, le=300)
    is_scoreboard_enabled: bool = True
    block_old_code: bool = True
    problems: List[ContestProblemInput] = Field(default_factory=list)
    allowed_user_ids: List[int] = Field(default_factory=list)
    allowed_classroom_ids: List[int] = Field(default_factory=list)


class ContestUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    penalty_minutes: Optional[int] = Field(None, ge=0, le=120)
    freeze_before_end_minutes: Optional[int] = Field(None, ge=0, le=300)
    is_hidden: Optional[bool] = None
    block_old_code: Optional[bool] = None
    problems: Optional[List[ContestProblemInput]] = None


class ContestAddUsersRequest(BaseModel):
    user_ids: List[int] = Field(default_factory=list)
    usernames: List[str] = Field(default_factory=list)  # username or email


class ContestAddClassroomRequest(BaseModel):
    classroom_id: int


# --- Classrooms & Assignments ---
class ClassroomCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    description: str = ""


class JoinClassroomRequest(BaseModel):
    join_code: str = Field(..., min_length=4, max_length=16)


class AddStudentRequest(BaseModel):
    username_or_email: str = Field(..., min_length=2)


class AssignmentCreateRequest(BaseModel):
    classroom_id: int
    title: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    due_at: Optional[str] = None
    problem_ids: List[int] = Field(default_factory=list)


# --- Admin Settings ---
class SystemSettingsUpdateRequest(BaseModel):
    settings: Dict[str, str]
