# Noka JUDGE — REST API Specification

Base URL: `/api/v1`  
OpenAPI / Swagger UI (Development): `http://localhost:8000/docs`

## Nhóm Endpoint chính

### 1. Authentication (`/api/v1/auth`)
- `POST /auth/register` — Đăng ký tài khoản học sinh (nếu được bật).
- `POST /auth/login` — Đăng nhập, trả về Bearer JWT token và thông tin user + roles.
- `GET /auth/me` — Lấy thông tin tài khoản hiện tại.

### 2. Users (`/api/v1/users`)
- `GET /users` — Danh sách người dùng (Admin/Teacher).
- `POST /users` — Tạo tài khoản (Admin/Teacher tạo học sinh; chỉ Admin cấp quyền teacher/admin).
- `PATCH /users/{user_id}` — Cập nhật trạng thái/vai trò (Admin).

### 3. Problems (`/api/v1/problems`)
- `GET /problems` — Danh sách bài tập có lọc (search, tag, difficulty, status, visibility), sắp xếp (code, title, difficulty, ac_rate), phân trang.
- `GET /problems/{code_or_id}` — Chi tiết bài tập + sample testcases (không bao giờ trả hidden testcases cho student).
- `POST /problems` — Tạo bài tập (Admin/Teacher).
- `PUT /problems/{id}` — Cập nhật bài tập (Admin/Owner Teacher).
- `DELETE /problems/{id}` — Xóa mềm bài tập (Admin/Owner Teacher).

### 4. Testcases (`/api/v1/testcases`)
- `GET /testcases/problem/{problem_id}` — Danh sách testcase (chỉ Admin/Teacher; Student bị chặn 403).
- `POST /testcases/problem/{problem_id}` — Thêm testcase thủ công.
- `POST /testcases/problem/{problem_id}/upload-zip` — Upload file ZIP chứa cặp `01.in`/`01.out`, tự động ghép cặp và cảnh báo file lỗi.
- `PUT /testcases/{testcase_id}` — Sửa trực tiếp input/output, subtask, sample/hidden.
- `POST /testcases/problem/{problem_id}/save-all` — Lưu sắp xếp/nhóm điểm hàng loạt.
- `DELETE /testcases/{testcase_id}` — Xóa testcase.
- `GET /testcases/problem/{problem_id}/backup` — Tải toàn bộ testcase dạng ZIP.
- `POST /testcases/problem/{problem_id}/groups` — Tạo nhóm subtask.

### 5. Advanced Testcase Generator (`/api/v1/testcase-generator`)
- `GET /testcase-generator/templates` — Danh sách Built-in Templates (Mode C) và các nhóm phân bố Advanced Randomization.
- `POST /testcase-generator/generate` — Chạy sinh testcase (Mode A / Mode B / Mode C) trong sandbox, trả về `batch_id` cùng preview từng test (thành công/thất bại, kích thước, thời gian).
- `POST /testcase-generator/batches/{batch_id}/save` — Lưu các testcase đã chọn vào bài tập (không tự ghi đè, yêu cầu xác nhận).
- `GET /testcase-generator/batches/{batch_id}/download` — Tải bộ testcase vừa sinh dạng ZIP.

### 6. Submissions (`/api/v1/submissions`)
- `POST /submissions` — Nộp bài chấm thật (đưa vào Judge Queue).
- `POST /submissions/run-sample` — Chạy thử trên sample input.
- `GET /submissions` — Danh sách bài nộp có lọc (user, problem, language, verdict, date).
- `GET /submissions/{id}` — Chi tiết bài nộp (ẩn thông tin hidden testcase đối với học sinh).

### 7. Contests (`/api/v1/contests`)
- `GET /contests`, `POST /contests`, `GET /contests/{id}`, `POST /contests/{id}/register`, `GET /contests/{id}/scoreboard`.

### 8. Classrooms & Assignments (`/api/v1/classrooms`, `/api/v1/assignments`)
- `GET /classrooms`, `POST /classrooms`, `POST /classrooms/join`, `POST /classrooms/{id}/students/import` (CSV/Excel), `GET /classrooms/{id}/progress`.
- `POST /assignments`, `GET /assignments/classroom/{classroom_id}`.

### 9. Admin (`/api/v1/admin`)
- `GET /admin/stats`, `GET /admin/settings`, `PUT /admin/settings`, `GET /admin/audit-logs`.
