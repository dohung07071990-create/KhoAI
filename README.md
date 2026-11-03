# KhoAI v0.5.1 — External USB Camera Security

## 1. Phạm vi hiện tại

- Chỉ pipeline AI của **camera USB bên ngoài nhà kho** được triển khai trong phiên bản này.
- ESP32-CAM/camera bên trong kho không tham gia xử lý AI hiện tại.
- Luồng AI: OpenCV → YOLOv8n (person) → ByteTrack → Foot Point → Zone Manager → Alarm Manager → Event/Evidence.
- ByteTrack ID chỉ có ý nghĩa trong một luồng camera; không phải danh tính nhân viên và không tự liên kết với UID RFID.
- Hệ thống là prototype học tập, chưa được kiểm định để dùng làm hệ thống an ninh duy nhất.

## 2. Cài đặt và chạy trên Windows

Từ thư mục gốc dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r ai/requirements.txt
Copy-Item .env.example .env
```

Đặt các secret trong biến môi trường trước khi chạy (không commit `.env`):

```powershell
$env:KHOAI_ADMIN_TOKEN = "chuoi-bi-mat-quan-tri-dai-va-ngau-nhien"
$env:KHOAI_API_KEY = "api-key-rieng-cho-esp32"
$env:BUSINESS_TIMEZONE = "Asia/Ho_Chi_Minh"
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 3000
```

Mở `http://127.0.0.1:3000`. Lần đầu thao tác quản trị trên dashboard, trình duyệt yêu cầu nhập `KHOAI_ADMIN_TOKEN`; token được giữ trong `sessionStorage` của tab hiện tại. Sau request quản trị hợp lệ, backend cấp cookie phiên `HttpOnly` (8 giờ) để trình duyệt tải stream/ảnh mà không đưa token vào URL. Nếu chưa cấu hình token, các API ghi bị khóa (HTTP 503). Nếu token sai/thiếu, API ghi trả HTTP 401.

Lần chạy YOLO đầu tiên có thể cần tải `yolov8n.pt`. Camera USB phải được cắm vào máy đang chạy backend. Dùng `python -m ai.list_cameras` để kiểm tra index camera.

## 3. Bảo mật API — bắt buộc cấu hình

- Tất cả API quản trị yêu cầu header `X-Admin-Token` khớp `KHOAI_ADMIN_TOKEN`; backend cấp cookie `HttpOnly` cho các request media trong trình duyệt. Query-string token đã bị vô hiệu hóa để tránh rò rỉ qua lịch sử trình duyệt và access log; media sử dụng cookie HttpOnly hoặc header `X-Admin-Token`. tạo/xóa thẻ, kiểm tra truy cập thủ công, xác nhận cảnh báo, bật/tắt chống trộm, sửa vùng và nhận sự kiện tích hợp.
- `POST /api/rfid/scan` và `POST /api/device/heartbeat` luôn yêu cầu `X-API-Key` khớp `KHOAI_API_KEY`. Nếu chưa đặt key, endpoint thiết bị bị khóa; không còn chế độ bỏ qua key.
- API GET vẫn đọc được trong mạng nội bộ. Không mở cổng trực tiếp ra Internet; dùng firewall/VPN và HTTPS reverse proxy nếu truy cập từ xa. Token trong trình duyệt không thay thế HTTPS.
- Không dùng UID thẻ MIFARE Classic làm xác thực mật mã mạnh: UID có thể bị sao chép trên một số loại thẻ/thiết bị. Đây là giới hạn của prototype.

Ví dụ tạo thẻ (PowerShell):

```powershell
$h = @{ "X-Admin-Token" = $env:KHOAI_ADMIN_TOKEN }
$b = @{ uid="A1B2C3D4"; name="Nhan vien demo"; daily_quota=3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:3000/api/cards -Headers $h -ContentType "application/json" -Body $b
```

Ví dụ ESP32 gọi RFID phải gửi `X-API-Key: <KHOAI_API_KEY>`; firmware cần được cấu hình cùng giá trị. Không ghi key thật vào README hoặc Git.

## 4. Các API đang có

### Camera USB

- `GET /api/camera/status`
- `GET /api/camera/stream` — MJPEG stream
- `GET /api/camera/snapshot` — JPEG snapshot
- `GET /api/camera/zone`, `PUT /api/camera/zone`
- `PUT /api/camera/anti-theft`
- `GET /api/camera/events` — chỉ đọc; sự kiện được worker nền đồng bộ vào SQLite
- `GET /api/camera/heatmap`
- `GET /api/camera/evidence/{filename}`

### RFID, thẻ và cảnh báo

- `POST /api/rfid/scan` — bắt buộc `X-API-Key`
- `POST /api/device/heartbeat` — bắt buộc `X-API-Key`
- `GET /api/cards`, `POST /api/cards`, `DELETE /api/cards/{uid}`
- `POST /api/access/check`, `POST /api/access/associate` (liên kết thủ công UID vừa quẹt thành công với Track ID đang xuất hiện)
- `GET /api/logs`, `GET /api/scans`, `GET /api/stats`, `GET /api/status`
- `GET /api/alerts`, `POST /api/alerts/{event_id}/ack`
- `POST /api/events` — endpoint nhận sự kiện từ công cụ tích hợp, yêu cầu `X-Admin-Token`

Các route `/api/inventory`, `/api/inventory/compare`, `/api/security/events`, `/api/camera/devices` và `/api/camera/source` **không có trong bản hiện tại**. Route `/api/access/associate` đã được khôi phục theo hướng liên kết thủ công có kiểm tra lượt quẹt hợp lệ gần đây và Track ID hiện còn xuất hiện. Model/bảng cũ liên quan được giữ lại ở mức tương thích dữ liệu, không được xem là tính năng đang hoạt động. Không có API `/api/camera/stream.mjpg` hoặc file `snapshot.jpg`; route đúng là `/api/camera/stream` và `/api/camera/snapshot`.

## 5. Logic truy cập và giới hạn RFID–camera

- `/api/rfid/scan` xác thực UID và quyết định cho phép/từ chối.
- Một lần quẹt RFID không cho biết người nào trong hình đã quẹt. Muốn liên kết cần một quy trình xác nhận `track_id` rõ ràng; phiên bản hiện tại chưa tự động ghép người trong video với UID.
- Vì vậy không được diễn giải cảnh báo người chưa liên kết thành kết luận chắc chắn người đó không có thẻ.
- Kiểm tra hạn mức dùng ngày theo `Asia/Ho_Chi_Minh`; việc tăng `used_today` được thực hiện trong transaction ghi khóa và conditional UPDATE để tránh hai lượt quẹt đồng thời cùng vượt hạn mức.
- `expires_at` nhận ngày ISO `YYYY-MM-DD`; `color` chỉ nhận tên chữ ngắn hoặc mã hex `#RRGGBB`.
- So sánh số người với số lượt quẹt trong 120 giây gần nhất chỉ là heuristic phát hiện **nghi vấn**, không phải xác minh tailgating hay danh tính.

## 6. Vùng bảo vệ

1. Mở dashboard, chọn camera USB ngoài.
2. Chọn “Vẽ vùng bảo vệ”, bấm ít nhất 3 điểm bao quanh khu vực cần bảo vệ trên mặt sàn trong ảnh camera.
3. Lưu vùng. Tọa độ được lưu chuẩn hóa trong `ai/zone.json`.
4. Lịch vùng theo `Asia/Ho_Chi_Minh`: 06:00–17:59 dùng vùng gốc; 18:00–05:59 vùng ALARM mở rộng theo hệ số cấu hình hiện tại. Vùng WARNING nằm ngoài vùng ALARM.
5. Bật/tắt chống trộm độc lập trên dashboard. Khi bật, người đã hiện diện trong vùng ALARM cũng được đánh giá.

Vùng chỉ chính xác khi camera cố định và khu vực cần bảo vệ nhìn thấy rõ. Camera USB bên ngoài không thể quan sát xuyên tường hoặc giám sát bốn phòng bên trong.

## 7. Docker

Dockerfile cài dependencies AI, dùng `opencv-python-headless`, copy thư mục `ai/` và không copy `.env` vào image. `docker-compose.yml` khai báo volume dữ liệu và thiết bị `/dev/video0` cho Linux:

```bash
cp .env.example .env
# sửa KHOAI_ADMIN_TOKEN và KHOAI_API_KEY trong .env
 docker compose up --build -d
```

Trên Linux, sửa mapping `/dev/video0` theo thiết bị thực tế. Docker Desktop trên Windows không tự động cấp webcam USB Linux device theo cấu hình này; chạy trực tiếp trên Windows thường phù hợp hơn cho demo webcam. Dữ liệu SQLite và ảnh bằng chứng nằm trong volume `/app/data`.

## 8. Kiểm thử và giới hạn

Chạy test:

```bash
python -m pytest -q
```

Test tự động không thay thế thử nghiệm camera USB, RFID, servo, còi và mạng LAN thực tế. Camera offline/reconnect, chất lượng nhận diện, độ trễ và vùng giám sát phải được kiểm tra tại vị trí lắp đặt. Mã UID của thẻ có thể bị clone; muốn tăng bảo mật cần dùng thẻ/giao thức xác thực mật mã phù hợp và phần cứng tương thích.

Worker nền tự dọn `access_logs` và `security_events` quá thời hạn `KHOAI_LOG_RETENTION_DAYS` (mặc định 365 ngày); đặt `0` hoặc số âm để tắt. Sao lưu DB trước khi thay đổi chính sách lưu trữ.


## v0.5.2 – hardening follow-up

- Các API đọc dữ liệu nhạy cảm (UID, log, lượt quẹt, cảnh báo, trạng thái camera) yêu cầu `X-Admin-Token`.
- Luồng/ảnh camera dùng tham số `token` vì thẻ `<img>` không gửi được header tùy chỉnh. Token trên URL có thể xuất hiện trong browser history/access log; chỉ dùng trong LAN demo, không triển khai Internet theo cấu hình này.
- `tools/color_detect.py` cần biến môi trường `KHOAI_ADMIN_TOKEN` giống backend.
- Docker mặc định không ánh xạ webcam. Trên Linux có webcam `/dev/video0`, chạy thêm `docker compose -f docker-compose.yml -f docker-compose.linux-camera.yml up --build`. Docker Desktop trên Windows không hỗ trợ ánh xạ webcam USB theo cách `/dev/video0`; chạy camera/backend trực tiếp trên Windows hoặc dùng Linux host.
- Token dùng chung qua HTTP chỉ phù hợp demo LAN tin cậy; triển khai thực tế cần HTTPS, rate limiting, quản lý token riêng và kiểm soát mạng.


### Kiểm thử và tài liệu API (v0.5.4)
- Cài thư viện kiểm thử bằng `pip install -r requirements-dev.txt`; image Docker production chỉ cài `requirements.txt`.
- `/docs`, `/redoc` và `/openapi.json` tắt mặc định. Chỉ bật trong môi trường phát triển bằng `KHOAI_ENABLE_OPENAPI=1`.
- Công cụ vẽ vùng khi server chạy: `python -m ai.draw_zone --server http://127.0.0.1:3000 --token "$env:KHOAI_ADMIN_TOKEN"` (PowerShell), hoặc đặt biến môi trường `KHOAI_ADMIN_TOKEN`. Token được gửi bằng header, không gắn vào URL.


### Kiểm thử xác thực frontend v0.5.4

Chạy kiểm thử JavaScript bằng Node.js (không cần thư viện npm):

```bash
node --test tests/test_frontend_auth.js
```

Kiểm thử backend dùng `pip install -r requirements-dev.txt` rồi `python -m pytest -q`.
