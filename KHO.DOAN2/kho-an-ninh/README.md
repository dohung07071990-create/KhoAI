# Kho thông minh - bản đầu (phần 3 và 4 + ý tưởng 6 tab)

```
server/main.py        FastAPI + SQLite, mọi endpoint, luật báo động, TIME_SCALE
server/static/        Web 6 tab (HTML/CSS/JS thuần)
tools/color_detect.py Nhận diện người Lego theo màu (OpenCV), gửi POST /api/events
tests/curl_test.sh    Giả lập ESP32 + camera bằng curl, chưa cần mạch
docs/                 Nháp giao diện + mô hình nhà kho
```

## Chạy
```
cd server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```
Mở http://localhost:8000. Cơ sở dữ liệu `kho.db` tự tạo. Rồi chạy `bash tests/curl_test.sh` ở cửa sổ khác và xem 6 tab thay đổi.

## Hợp đồng với ESP32
- `POST /api/rfid/scan` `{"uid":"AA11BB22","device_id":"esp32-door"}` → `{"allow":true,"reason":null,"name":"Minh","alarm":"off"}`
- `POST /api/device/heartbeat` `{"device_id":"esp32-door"}` → `{"alarm":"off|warning|severe"}` (gọi mỗi 5 giây)
- Lý do từ chối: `unknown_card`, `expired`, `quota_exhausted`.

## Phần 3 (server)
Checklist: cài FastAPI ✔, SQLite ✔, bảng thẻ + lịch sử quẹt ✔ (kèm permissions, pickup_orders, alerts, devices), nhận mã thẻ → kiểm tra → cho phép/từ chối → ghi lịch sử ✔, test bằng curl ✔.

## Phần 4 (web và mô hình)
Nháp trong `docs/wireframes.md`, web trong `server/static`, form cấp thẻ có đủ ô, mô hình trong `docs/mo_hinh_nha_kho.md`.
Địa chỉ camera nhập ngay trên tab Camera ngoài/trong (lưu trong trình duyệt).

## Lưu ý trung thực
Code **chưa được chạy thử trên server thật** (môi trường soạn không cài được FastAPI), mới kiểm cú pháp Python/JS. Bạn chạy lần đầu và gửi lỗi (nếu có) để mình sửa.
Ngưỡng màu HSV trong `color_detect.py` chỉ là giá trị khởi đầu, cần chỉnh theo đèn thật.
