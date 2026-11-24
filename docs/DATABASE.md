# Noka JUDGE — Database Design

Hệ thống sử dụng **PostgreSQL 16** với lược đồ chuẩn hóa, quản lý phiên bản bằng **Alembic** (`backend/migrations/`).

## Danh sách bảng (20 bảng)

| Nhóm | Bảng | Mô tả |
|---|---|---|
| Tài khoản & Quyền | `users`, `roles`, `user_roles` | Người dùng, 3 vai trò (`admin`, `teacher`, `student`), soft delete (`deleted_at`). |
| Bài tập & Thẻ | `problems`, `tags`, `problem_tags` | Đề bài Markdown/LaTeX, giới hạn thời gian/bộ nhớ, độ khó, visibility (`public`/`private`/`classroom`), checker. |
| Testcase & Subtask | `testcase_groups`, `testcases` | Phân nhóm subtask theo điểm, lưu khóa tệp (`input_storage_key`, `output_storage_key`) thay vì nhồi nội dung lớn vào DB, cờ `is_sample` và `is_hidden`. |
| Chấm bài | `submissions`, `submission_results` | Bài nộp lưu đường dẫn tệp source code (`source_storage_key`), trạng thái, verdict (`AC/WA/TLE/MLE/RE/CE/OLE/IE`), điểm, thời gian, bộ nhớ, kết quả từng testcase. |
| Kỳ thi | `contests`, `contest_problems`, `contest_participants` | Thời gian bắt đầu/kết thúc, chế độ public/private/classroom, penalty, đóng băng bảng xếp hạng (`freeze_before_end_minutes`). |
| Lớp học | `classrooms`, `classroom_students`, `assignments`, `assignment_problems` | Quản lý lớp học, mã tham gia (`join_code`), giao bài tập có deadline. |
| Vận hành | `announcements`, `audit_logs`, `system_settings` | Thông báo, nhật ký kiểm toán thao tác quan trọng, cấu hình tập trung (`site_name`, ...). |

## Quy tắc lưu trữ & Migration

- **Không lưu blob lớn trong DB**: Source code và file input/output testcase được lưu tại `storage/` (hoặc S3), DB chỉ lưu `*_storage_key` và kích thước byte.
- **Migration**: Chạy `./scripts/migrate.sh` (tương đương `alembic upgrade head`) trong container backend.
- **Sao lưu & Khôi phục**: Sử dụng `./scripts/backup_db.sh` (pg_dump nén `.sql.gz` vào `database/backups/`) và `./scripts/restore_db.sh <file>`.
