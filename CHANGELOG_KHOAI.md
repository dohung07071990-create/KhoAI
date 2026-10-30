# Changelog — KhoAI

## Bản nâng cấp prototype 0.2.0

### [MODIFIED] `ai/person_detector.py`
- Theo dõi thời gian hiện diện riêng cho từng `track_id`.
- Tạo sự kiện khi người vào vùng chưa được liên kết với thẻ hợp lệ.
- Tạo cảnh báo đứng lâu một lần trong mỗi lượt hiện diện.
- Thêm API nội bộ để liên kết UID thẻ với Track ID do người vận hành xác nhận.
- Hạ độ phân giải mặc định và cho phép cấu hình độ tin cậy, kích thước suy luận để chạy CPU.
- Trạng thái camera không tự chạy inference chỉ vì dashboard polling.

### [MODIFIED] `backend/app/main.py`
- Bổ sung `inventory` để đăng ký SKU/số lượng.
- Bổ sung endpoint đối chiếu số lượng và lưu sự kiện sai lệch vào SQLite.
- Bổ sung API liên kết thẻ với Track ID và API truy xuất cảnh báo.
- Bật SQLite WAL cho truy cập cục bộ đồng thời.

### [NEW] `frontend/index.html`, `frontend/app.js`
- Bổ sung màn hình hàng hóa và cảnh báo.
- Bổ sung form đăng ký SKU, so sánh số lượng và liên kết RFID với Track ID.

### [MODIFIED] `.env.example`, `README.md`
- Bổ sung cấu hình hiệu năng CPU, hướng dẫn API, kiểm thử và giới hạn đã biết.

## Chưa triển khai trong bản này
- Camera chưa tự đếm hàng hóa; số lượng thực tế hiện được nhập hoặc truyền từ tích hợp ngoài.
- Chưa có push notification qua Telegram/email/SMS; cảnh báo được ghi vào SQLite và hiển thị trong dashboard/API.
- Firmware ESP32 hiện vẫn xác thực thẻ độc lập; cần thay đổi giao thức nếu muốn firmware truyền Track ID hoặc đồng bộ trạng thái liên kết.
- Chưa có đăng nhập/phân quyền, HTTPS, chống giả mạo UID hoặc kiểm định an ninh thực tế.

## Bản 0.3.0 — sửa camera USB và vùng cấm
- `ai/person_detector.py` viết lại: luồng nền đọc camera + luồng AI; sửa vòng lặp chết (camera chỉ mở khi có stream, stream chỉ mở khi camera đã mở).
- `ai/camera_utils.py` (mới): dò camera tự động, thử nhiều backend, bỏ frame khởi động, ép MJPG; `ai/list_cameras.py` để tìm index đúng.
- Vùng cấm: tính cả người chưa có track ID, xử lý chân bị cắt ở đáy khung, lọc box quá nhỏ, trễ vào/ra theo frame, tự nạp lại `zone.json`, lưu `frame_size`.
- `ai/draw_zone.py`: dùng chung hàm mở camera, thêm `--server` (vẽ khi server đang chạy), undo, hiển thị vùng cũ.
- Phần init: `.env` thực sự được đọc (`ai/envfile.py`), `ai/__init__.py`, `backend/__init__.py`, `backend/app/__init__.py`, `lifespan` thay `on_event`, `init_db()` chạy trong lifespan.
- API mới: `GET /api/camera/devices`, `PUT /api/camera/source`, `GET /api/camera/snapshot.jpg`.
