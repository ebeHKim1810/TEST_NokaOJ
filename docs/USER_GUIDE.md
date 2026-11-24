# Noka JUDGE — Hướng dẫn sử dụng nhanh

## 1. Dành cho Học sinh
1. Đăng nhập tài khoản do giáo viên cấp hoặc tự đăng ký.
2. Vào **Bài tập (Problemset)** để lọc theo chủ đề, độ khó hoặc trạng thái giải.
3. Mở bài tập, chọn ngôn ngữ (`C++17`, `C++20`, `Python 3`), viết lời giải trong **Monaco Editor** (mã nháp được tự động lưu theo từng bài và ngôn ngữ).
4. Nhấn **Chạy thử (Run Sample)** để kiểm tra nhanh trên ví dụ, sau đó nhấn **Nộp bài (Submit)** để hệ thống chấm tự động.
5. Vào **Lớp học** và nhập mã lớp (Join Code) từ giáo viên để xem bài tập được giao và deadline.

## 2. Dành cho Giáo viên & Admin
1. **Tạo bài tập nhanh**: Vào **Quản trị → Bài tập → Tạo bài mới**, nhập nội dung bằng Markdown + công thức LaTeX (`$O(N \log N)$`), bật **Xem trước (Preview)** để kiểm tra hiển thị.
2. **Quản lý Testcase**: Mở tab **Testcases** của bài tập để:
   - Thêm từng test thủ công hoặc upload file ZIP có cặp `01.in` / `01.out`.
   - Chia nhóm điểm (**Subtask**), đánh dấu **Sample** hoặc **Hidden**.
   - Tải xuống toàn bộ testcase để sao lưu.
3. **Sinh Testcase tự động (Advanced Testcase Generator)**:
   - Nhấn nút **Generate Testcases**.
   - Chọn **Mode A** (nhập code AC + code Generator), **Mode B** (nhập code AC + cấu trúc ràng buộc), hoặc **Mode C** (chọn mẫu có sẵn như Array, Permutation, Tree, Graph, Matrix, Queries + phân bố biên/đặc biệt).
   - Hệ thống chạy Generator & Reference Solution trong sandbox an toàn, hiển thị **Testcase Review** để xem trước, chọn lọc, tải ZIP hoặc nhấn **Save Selected to Problem** (có bước xác nhận, không ghi đè dữ liệu cũ).
4. **Lớp học & Kỳ thi**: Tạo lớp học, import danh sách học sinh từ CSV/Excel, giao bài tập kèm hạn nộp hoặc tổ chức Contest có bảng xếp hạng và đóng băng điểm.

## 3. Đổi tên hệ thống (Branding)
Chỉ cần chỉnh sửa biến `APP_NAME` và `VITE_APP_NAME` trong tệp `.env` (hoặc mục **Cấu hình hệ thống** trong trang Admin) để đổi tên từ `Noka JUDGE` sang tên trung tâm/lớp học của bạn.
