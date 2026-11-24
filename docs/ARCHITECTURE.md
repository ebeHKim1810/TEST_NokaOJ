# Noka JUDGE — System Architecture

## 1. Tổng quan kiến trúc

Noka JUDGE được thiết kế theo mô hình **Monorepo đa dịch vụ độc lập** (decoupled services), sẵn sàng chạy gọn trên một VPS bằng Docker Compose và có thể tách riêng Frontend, Backend, Database và nhiều Judge Worker ra các máy chủ khác nhau khi mở rộng.

```
                   ┌──────────────────────────────┐
                   │     Nginx Reverse Proxy      │
                   │   (HTTPS / TLS / Rate Limit) │
                   └──────────────┬───────────────┘
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
   ┌──────────────────────────┐      ┌──────────────────────────┐
   │    Frontend (React SPA)  │      │   Backend API (FastAPI)  │
   │  Vite + TS + Tailwind    │─────▶│  REST /api/v1/* + RBAC   │
   │  Monaco Editor + KaTeX   │      │  Pydantic + Audit Logs   │
   └──────────────────────────┘      └──────┬───────────┬───────┘
                                            │           │
                       ┌────────────────────┘           └──────────────┐
                       ▼                                               ▼
         ┌──────────────────────────┐                    ┌──────────────────────────┐
         │       PostgreSQL 16      │                    │      Redis 7 Queue       │
         │   (20 bảng chuẩn hóa)    │                    │  noka:judge:submissions  │
         └──────────────────────────┘                    └──────────────┬───────────┘
                       ▲                                                │
                       │                                                ▼
         ┌──────────────────────────┐                    ┌──────────────────────────┐
         │    Storage Abstraction   │◀──────────────────▶│  Judge Worker (Độc lập)  │
         │ Local FS / S3-compatible │                    │  Compiler + Checker      │
         └──────────────────────────┘                    │  Testcase Generator      │
                                                         └──────────────┬───────────┘
                                                                        ▼
                                                         ┌──────────────────────────┐
                                                         │   Docker Sandbox Runner  │
                                                         │  --network none, non-root│
                                                         │  CPU / RAM / Time Limits │
                                                         └──────────────────────────┘
```

## 2. Nguyên tắc phân tách trách nhiệm

1. **Frontend (`frontend/`)**: Chỉ giao tiếp với Backend qua REST API `/api/v1/*`. Không bao giờ truy cập trực tiếp database hay Judge Worker. Tên thương hiệu được tập trung tại `frontend/src/config/brand.ts` và biến môi trường `VITE_APP_NAME`.
2. **Backend API (`backend/`)**: Quản lý xác thực (Argon2/scrypt + JWT), phân quyền RBAC (`admin`, `teacher`, `student`), kiểm tra dữ liệu đầu vào (Pydantic v2), quản lý bài tập, testcase, lớp học, contest, lưu trữ tệp qua `StorageBackend`, ghi `audit_logs` và đẩy job chấm bài vào Redis Queue. **Không bao giờ chạy mã nguồn người dùng trong tiến trình FastAPI.**
3. **Judge Worker (`judge/`)**: Tiến trình độc lập tiêu thụ job từ Redis Queue (hoặc DB queue fallback). Thực hiện biên dịch (`compilers/`), chạy mã trong Docker sandbox không có mạng (`sandbox/`), so khớp output bằng Standard/Custom Checker (`checkers/`), và cập nhật kết quả chi tiết từng testcase vào PostgreSQL.
4. **Advanced Testcase Generator (`judge/generators/`)**: Module độc lập hỗ trợ 3 chế độ sinh testcase thực:
   - **Mode A (Custom Generator)**: Chạy mã sinh input + chạy Reference Solution (AC) trong sandbox để sinh expected output.
   - **Mode B (Structured Constraints + Validator)**: Sinh dữ liệu theo schema ràng buộc, kiểm tra bằng validator, rồi chạy Reference Solution.
   - **Mode C (Built-in Templates + Advanced Randomization)**: Sinh theo nhóm phân bố (min, max, random, boundary, edge, duplicate, sorted, reverse, sparse/dense graph, chain/star/balanced tree...) rồi chạy Reference Solution.
5. **Storage Abstraction (`backend/app/core/storage.py`)**: Giao diện `BaseStorage` tách biệt hoàn toàn giữa `LocalFileStorage` (mặc định) và `S3Storage` (chuẩn bị sẵn cho MinIO / AWS S3 / Cloudflare R2).
