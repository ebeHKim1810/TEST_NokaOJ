# Noka JUDGE — Security Architecture

## 1. Bảo mật thực thi mã không đáng tin cậy (Sandbox)

Cả **bài nộp của học sinh**, **Custom Generator** và **Reference Solution** đều được xem là mã không đáng tin cậy:

- **Tách tiến trình**: Backend FastAPI không bao giờ biên dịch hoặc chạy mã người dùng. Mọi thực thi diễn ra trong **Judge Worker** tách biệt.
- **Cô lập Docker Sandbox (Production)**:
  - `--network none` — cấm hoàn toàn truy cập internet và mạng nội bộ (không thể kết nối PostgreSQL/Redis/Backend).
  - `--read-only` kèm thư mục `/work` tạm thời giới hạn dung lượng (`tmpfs`).
  - `--user 65534:65534` (nobody) — tuyệt đối không chạy với quyền `root`.
  - `--cap-drop=ALL` và `--security-opt=no-new-privileges:true`.
  - `--cpus=1.0`, `--memory=<limit>m`, `--memory-swap=<limit>m`, `--pids-limit=64` — chống fork bomb và cạn kiệt tài nguyên.
  - Tự động hủy container và dọn thư mục làm việc riêng ngay khi vượt quá thời gian hoặc hoàn tất.
- **Giới hạn dung lượng Output (OLE)**: Cắt và trả về `OLE` nếu stdout vượt ngưỡng cấu hình (`JUDGE_MAX_OUTPUT_BYTES`).

## 2. Xác thực & Phân quyền (Auth & RBAC)

- **Băm mật khẩu**: Sử dụng Argon2id (`argon2-cffi`) làm chuẩn chính (có fallback `scrypt` an toàn của stdlib khi chạy môi trường tối giản không cài thư viện ngoài).
- **Token**: JWT ký bằng `SECRET_KEY` đọc từ biến môi trường, không hardcode trong mã nguồn.
- **RBAC 3 cấp (`admin`, `teacher`, `student`)**:
  - Học sinh không thể gọi Admin API, không thể truy cập `/api/v1/testcases/problem/{id}` và không bao giờ nhận được nội dung hidden testcase hay expected output.
  - Giáo viên chỉ sửa bài tập, lớp học, contest do mình quản lý (trừ Admin có toàn quyền).

## 3. Bảo vệ tầng API & Dữ liệu

- **Chống SQL Injection**: 100% truy vấn sử dụng tham số hóa (`%s` / `?`).
- **Validation**: Mọi payload đều kiểm tra chặt bằng Pydantic v2 và giới hạn kích thước upload file ZIP/CSV.
- **Rate Limiting**: Middleware giới hạn số request/phút toàn cục và giới hạn riêng tần suất nộp bài.
- **Audit Log**: Tự động ghi nhật ký vào bảng `audit_logs` cho các thao tác nhạy cảm (tạo/xóa bài tập, sửa testcase, sinh testcase, đổi phân quyền, đổi cấu hình hệ thống).
