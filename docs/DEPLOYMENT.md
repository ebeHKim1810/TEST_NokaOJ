# Noka JUDGE — Hướng dẫn Triển khai (Local & VPS Production)

Hướng dẫn này được viết từng bước cho người mới, không yêu cầu kinh nghiệm DevOps chuyên sâu.

---

## Phần 1: Chạy trên máy tính Windows (Local Development)

### Bước 1: Cài đặt Docker Desktop
1. Tải và cài đặt **Docker Desktop for Windows** (bật sẵn WSL2 khi cài).
2. Mở Docker Desktop và chờ biểu tượng cá voi chuyển sang trạng thái Running.

### Bước 2: Tạo tệp cấu hình `.env`
Mở PowerShell tại thư mục `noka-judge`:
```powershell
Copy-Item .env.example .env
```
Mở `.env` bằng Notepad hoặc VS Code và đổi `SECRET_KEY`, `POSTGRES_PASSWORD` thành chuỗi ngẫu nhiên của bạn.

### Bước 3: Khởi động hệ thống
```powershell
.\scripts\start.ps1
```
(Hoặc trên Linux/WSL2/macOS: `./scripts/start.sh`)

### Bước 4: Tạo tài khoản Admin đầu tiên (không dùng mật khẩu mặc định)
```powershell
docker compose exec backend python /app/scripts/create_admin.py
```
Nhập `username`, `email` và `password` mạnh theo hướng dẫn trên màn hình.

### Bước 5: Mở trình duyệt
- Giao diện web: `http://localhost:5173` (dev) hoặc `http://localhost` (prod)
- Tài liệu API: `http://localhost:8000/docs`

---

## Phần 2: Triển khai lên VPS (Ubuntu 22.04 / 24.04)

### Bước 1: Thuê VPS & Cài Docker
Khuyến nghị tối thiểu: **2 vCPU, 4 GB RAM, 40 GB SSD** (đủ chạy cho lớp 50–100 học sinh).
Đăng nhập SSH vào VPS và chạy:
```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Đăng xuất rồi đăng nhập lại để quyền docker có hiệu lực
```

### Bước 2: Cấu hình Firewall (UFW)
Chỉ mở 3 cổng cần thiết (SSH 22, HTTP 80, HTTPS 443):
```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
```
Không mở cổng `5432` (PostgreSQL) hoặc `6379` (Redis) ra ngoài internet.

### Bước 3: Kết nối Tên miền (Domain)
Tại trang quản trị DNS của nhà cung cấp tên miền (Cloudflare, Namecheap, Mat Bao...):
- Tạo bản ghi `A`: Host = `judge` (hoặc `@`), Value = `<IP công khai của VPS>`, TTL = Auto.
- Đợi 2–5 phút, kiểm tra bằng lệnh `ping judge.tenmiencuaban.com`.

### Bước 4: Tải mã nguồn & Cấu hình Production
```bash
cd /opt
# Copy thư mục noka-judge lên VPS (qua git hoặc scp)
cd /opt/noka-judge
cp .env.example .env
nano .env
```
Trong `.env`, cập nhật:
- `APP_ENV=production`
- `SECRET_KEY=<chuỗi ngẫu nhiên 64 ký tự>`
- `POSTGRES_PASSWORD=<mật khẩu mạnh>`
- `CORS_ORIGINS=https://judge.tenmiencuaban.com`
- `DOMAIN_NAME=judge.tenmiencuaban.com`
- `CERTBOT_EMAIL=emailcuaban@domain.com`

### Bước 5: Build ảnh Sandbox & Khởi động Production
```bash
docker build -t noka-judge-sandbox:latest -f infrastructure/docker/sandbox.Dockerfile .
docker compose -f docker-compose.prod.yml up -d --build
./scripts/migrate.sh
docker compose -f docker-compose.prod.yml exec backend python /app/scripts/create_admin.py
```

### Bước 6: Bật HTTPS miễn phí với Let's Encrypt (Certbot)
```bash
sudo apt install -y certbot
# Tạm dừng nginx để cấp chứng chỉ lần đầu
docker compose -f docker-compose.prod.yml stop nginx
sudo certbot certonly --standalone -d judge.tenmiencuaban.com -m emailcuaban@domain.com --agree-tos --non-interactive
# Bật lại nginx (mount /etc/letsencrypt tự động trong docker-compose.prod.yml)
docker compose -f docker-compose.prod.yml start nginx
```
Thiết lập tự gia hạn SSL định kỳ mỗi ngày bằng cron:
```bash
(crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && docker compose -f /opt/noka-judge/docker-compose.prod.yml exec -T nginx nginx -s reload") | crontab -
```

### Bước 7: Sao lưu & Khôi phục Database
- Sao lưu ngay: `./scripts/backup_db.sh` (tệp lưu tại `database/backups/`).
- Khôi phục: `./scripts/restore_db.sh database/backups/noka_judge_YYYYMMDD_HHMMSS.sql.gz`.
- Khuyến nghị thêm cron backup mỗi đêm lúc 02:00.
