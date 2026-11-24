# Noka JUDGE

Hệ thống **Online Judge (OJ)** hoàn chỉnh phục vụ giảng dạy lập trình, luyện thuật toán, tổ chức kỳ thi và chấm bài tự động.

- **Triết lý thiết kế**: Simple but powerful — giao diện tối giản, chuyên nghiệp (Light/Dark mode, bảng màu trung tính + Pastel Blue/Green/Pink/Orange, font Inter & JetBrains Mono, icon Lucide).
- **Cấu hình thương hiệu tập trung**: Đổi tên dự án tại một nơi duy nhất qua `.env` (`APP_NAME`, `VITE_APP_NAME`) và `frontend/src/config/brand.ts`.

## Tính năng chính

- **Phân quyền 3 vai trò (RBAC)**: Administrator, Teacher, Student. Bảo vệ tuyệt đối hidden testcase.
- **Problemset & Monaco Editor**: Bảng lọc/sắp xếp/phân trang, hỗ trợ Markdown + LaTeX, tự động lưu code nháp theo bài & ngôn ngữ, chạy thử sample, hỗ trợ `C++17`, `C++20`, `Python 3`.
- **Admin Problem & Testcase Manager**: Tạo/sửa bài tập nhanh có Preview, thêm testcase thủ công, upload ZIP tự động ghép cặp (`01.in` ↔ `01.out`) kèm cảnh báo lỗi rõ ràng, chia Subtask, sao lưu ZIP.
- **Advanced Testcase Generator**:
  - **Mode A**: Custom Generator + Reference Solution (AC).
  - **Mode B**: Structured Constraints + Input Validator + Reference Solution.
  - **Mode C**: 11 Built-in Templates (Integer, Array, Increasing, Decreasing, Permutation, String, Graph, Tree, Matrix, Queries, Edge Cases) + Advanced Randomization theo phân bố nhóm.
  - Chạy hoàn toàn trong sandbox, có trang Review (xem trước, chọn lọc, tải ZIP, lưu có xác nhận).
- **Judge Engine độc lập**: Biên dịch và chấm thật trong sandbox cô lập (Docker `--network none`, non-root, giới hạn CPU/RAM/Time/Output), hỗ trợ đầy đủ verdict `AC`, `WA`, `TLE`, `MLE`, `RE`, `CE`, `OLE`, `IE`, subtask & custom checker.
- **Contest & Classroom**: Tổ chức kỳ thi (scoreboard, penalty, freeze), quản lý lớp học, mã tham gia, import danh sách học sinh CSV/Excel, giao bài tập kèm deadline và theo dõi tiến độ.

## Khởi chạy nhanh (Docker Desktop / WSL2 / Linux)

```bash
# 1. Tạo file môi trường
cp .env.example .env

# 2. Khởi chạy toàn bộ hệ thống (PostgreSQL, Redis, Backend, Judge Worker, Frontend)
./scripts/start.sh        # Linux / macOS / WSL2
# hoặc trên Windows PowerShell:
# .\scripts\start.ps1

# 3. Tạo tài khoản Admin đầu tiên (tương tác an toàn, không hardcode mật khẩu)
docker compose exec backend python /app/scripts/create_admin.py
```

Mở trình duyệt tại:
- Web UI: `http://localhost:5173`
- API Docs (Swagger): `http://localhost:8000/docs`

## Tài liệu chi tiết

- [Kiến trúc hệ thống](docs/ARCHITECTURE.md)
- [Thiết kế cơ sở dữ liệu](docs/DATABASE.md)
- [Đặc tả REST API](docs/API.md)
- [Hướng dẫn triển khai Local & VPS (Domain + HTTPS + Firewall)](docs/DEPLOYMENT.md)
- [Kiến trúc bảo mật](docs/SECURITY.md)
- [Hướng dẫn sử dụng](docs/USER_GUIDE.md)
