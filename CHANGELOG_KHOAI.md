<<<<<<< HEAD
# KhoAI Changelog

## v0.5.4 – Authentication race and credential hardening
- Sửa race condition đăng nhập: chỉ công bố token sau khi `/api/status` xác minh thành công; các request đồng thời dùng chung một Promise và chỉ xóa đúng token vừa bị từ chối.
- Giữ candidate khi server tạm thời không phản hồi để polling có thể thử xác minh lại mà không mở prompt mới; hủy hoặc token sai sẽ chặn prompt lặp trong phiên trang hiện tại.
- Media xác thực bằng cookie HttpOnly hoặc header; vô hiệu hóa token trên query string.
- Xác thực cookie/header theo từng nguồn, cookie cũ sai không che khuất header hợp lệ.
- Dùng `hmac.compare_digest` trên bytes UTF-8 để xử lý đầu vào Unicode an toàn.
- `alerts_today` chỉ đếm `warning` và `severe`.
- Bổ sung 3 kiểm thử backend và 3 kiểm thử JavaScript cho đăng nhập đồng thời, token cũ và hủy prompt.
- Cập nhật version API lên 0.5.4.

## v0.5.3 – Frontend auth, alerts and deployment fixes
- Khôi phục token khi reconnect stream; xác thực frontend dùng một prompt single-flight và không lặp prompt sau khi hủy/sai token.
- Bộ đếm cảnh báo chỉ tính warning/severe; API alerts mặc định ẩn info và hỗ trợ lọc severity.
- Công cụ draw_zone hỗ trợ --token hoặc KHOAI_ADMIN_TOKEN cho snapshot và cập nhật vùng.
- Tắt OpenAPI docs mặc định; có thể bật trong môi trường phát triển bằng KHOAI_ENABLE_OPENAPI=1.
- Tách pytest/httpx sang requirements-dev.txt để Docker image production không cài thư viện test.

=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
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
<<<<<<< HEAD


## Bản tổng hợp camera USB + nền tảng đánh giá hành vi
- Tách worker render MJPEG khỏi worker suy luận YOLO/ByteTrack; mặc định render 20 FPS và JPEG quality 74, cấu hình qua `.env`.
- Giữ các tính năng camera USB, vùng bảo vệ, tracking, sự kiện, heatmap và ảnh bằng chứng.
- Thêm `ai/behavior_analyzer.py` để đánh giá nhãn hành động do mô hình khác cung cấp theo quyền/khu vực/lệnh công việc.
- Chưa tích hợp hoặc huấn luyện mô hình nhận diện hành động video; xem `docs/action-recognition-roadmap.md`.
- Không thay đổi firmware ESP32-RFID và ESP32-CAM.


## Bản 0.4.0 — Zone Manager và Alarm Manager
- Thêm lịch vùng theo giờ Việt Nam: ban ngày 06:00–17:59; ban đêm 18:00–05:59. Vùng ALARM ban đêm được mở rộng 1,15 lần quanh trọng tâm đa giác gốc.
- Thêm vùng WARNING mở rộng 1,12 lần ngoài vùng ALARM; vùng ALARM tiếp tục dùng hysteresis theo Track ID để xác nhận vào/ra.
- Thêm trạng thái tổng hợp `SAFE` / `WARNING` / `ALARM`; nhiều người được đánh giá theo mức nguy hiểm cao nhất.
- Thêm công tắc chống trộm độc lập với lịch vùng và API `PUT /api/camera/anti-theft`. Bật hệ thống sẽ đánh giá cả người đã có mặt trong vùng ALARM.
- Dashboard hiển thị trạng thái an ninh, lịch vùng và vùng WARNING nét đứt; giữ nguyên frontend chính và firmware.
- Bổ sung kiểm thử cho lịch vùng, mở rộng đa giác, hành vi bật chống trộm khi người đã ở trong vùng.


## v0.5.0 — External USB Camera Security
- Chốt phạm vi AI ở camera USB bên ngoài nhà kho; ESP32-CAM/camera trong kho không tham gia pipeline AI hiện tại.
- Bổ sung sự kiện `camera_offline` khi camera không mở được hoặc mất luồng hình ảnh.
- Bổ sung sự kiện `camera_recovered` khi camera kết nối lại sau một lần mất kết nối.
- Tránh phát sinh lặp sự kiện trong cùng một đợt mất kết nối.
- API camera status công bố `camera_role=external_usb` và `camera_health`.
- Giữ nguyên YOLOv8n, ByteTrack, Foot Point, Zone Manager, Alarm Manager, giao diện chính và firmware hiện có.


## v0.5.1 — Security, data integrity and deployment hardening
- Khôi phục `POST /api/access/associate` và form dashboard để người vận hành liên kết UID vừa quẹt thành công với Track ID còn hiện diện; không tự suy đoán danh tính.
- Bắt buộc `KHOAI_ADMIN_TOKEN` cho mọi API ghi từ dashboard; bắt buộc `KHOAI_API_KEY` cho `/api/rfid/scan` và heartbeat thiết bị. Khi thiếu secret, endpoint fail-closed.
- Sửa các điểm chèn dữ liệu động trong dashboard bằng HTML escaping.
- Chuẩn hóa ngày theo `Asia/Ho_Chi_Minh`; xác thực `expires_at` và `color`; tiêu thụ quota bằng transaction `BEGIN IMMEDIATE` + conditional UPDATE.
- Camera events được đồng bộ nền; GET `/api/camera/events` chỉ đọc. Thêm `source_event_id` UNIQUE để chống ghi trùng.
- Tailgating compatibility heuristic dùng cửa sổ quẹt hợp lệ 120 giây và chỉ tạo cảnh báo nghi vấn cần xác minh, không dùng tổng lượt quẹt cả ngày.
- Docker image gồm mã AI, OpenCV headless, volume dữ liệu và cấu hình thiết bị qua Compose; không COPY `.env` vào image.
- Stream MJPEG chuyển sang async generator với frame wait trong worker thread; frontend reconnect theo exponential backoff.
- Thêm dọn log cũ định kỳ, mặc định giữ 365 ngày (`KHOAI_LOG_RETENTION_DAYS`).
- Dọn Manus artifacts, database/cache khỏi gói phát hành; đồng bộ version API lên 0.5.1.
- Giữ các bảng inventory/permissions cũ để tương thích dữ liệu, nhưng không quảng bá endpoint inventory chưa tồn tại.

## v0.5.2 – Regression fixes and read API hardening

- Phân loại `low`/`info` thành sự kiện thông tin; chỉ `medium`/`warning` mới nâng WARNING và `high`/`critical`/`severe` nâng ALARM.
- Bảo vệ các API đọc chứa UID, lịch sử truy cập, cảnh báo và trạng thái camera bằng `X-Admin-Token`; các endpoint ảnh/stream dùng query token do giới hạn của thẻ ảnh HTML.
- Sửa công cụ `color_detect.py` gửi token quản trị và kiểm tra HTTP status.
- Đồng bộ lại metadata bằng chứng nếu ảnh được gắn sau lần ghi sự kiện đầu tiên.
- Sửa fixture test để tắt camera bằng biến module đã được nạp; bổ sung kiểm thử bảo mật và đồng bộ sự kiện.
- Không ánh xạ webcam trong Docker Compose mặc định; bổ sung override riêng cho Linux.
- Sửa nhãn mã lý do, tránh đóng/mở lại dropdown Track ID nếu danh sách không đổi, và dùng text thô với `textContent`.


## v0.5.5 – Frontend POST helper regression fix

- Khôi phục helper `post()` dùng chung `api()` để giữ xác thực cho các thao tác POST JSON (xác nhận cảnh báo, cấp thẻ).
- Bổ sung kiểm thử hồi quy xác minh method, header JSON, admin token và request body của `post()`.
- Bổ sung thông báo lỗi trên giao diện khi xác nhận cảnh báo hoặc xóa thẻ thất bại.
=======
>>>>>>> 889d624ef29217e05c01da0b46d761ffd4ee4920
