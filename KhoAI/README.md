# Kho AI — nguyên mẫu kiểm soát kho

Bản mẫu kết hợp FastAPI + SQLite, giao diện HTML/CSS/JavaScript, YOLO pretrained cho camera USB, firmware ESP32/RC522/servo/còi và ESP32-CAM. **Mã và hướng dẫn có sẵn; chưa thể nạp hoặc kiểm tra mạch/camera vật lý trong môi trường này.** Preview đám mây chỉ xem giao diện/API mẫu; camera USB và board trong mạng LAN cần chạy server trên máy tính cùng mạng với thiết bị.

## Chạy server và web

Cần Python 3.10 trở lên. Từ thư mục gốc dự án:

```bash
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 3000
```

Mở `http://localhost:3000`. Tài liệu API tự sinh ở `http://localhost:3000/docs`. CSDL SQLite mặc định nằm ở `data/khoai.sqlite3`; có thể đổi đường dẫn bằng biến `DB_PATH`. Thời điểm và thống kê dùng `BUSINESS_TIMEZONE`, mặc định `Asia/Ho_Chi_Minh`.

## Kiểm thử không cần mạch

Cấp một UID thẻ thử:

```bash
curl -X POST http://localhost:3000/api/cards \
  -H 'Content-Type: application/json' \
  -d '{"uid":"A1B2C3D4","name":"Nguyen Van A","age":28}'
```

Kiểm tra UID hợp lệ (API sẽ ghi lịch sử):

```bash
curl -X POST http://localhost:3000/api/access/check \
  -H 'Content-Type: application/json' \
  -d '{"uid":"A1B2C3D4"}'
```

Thử UID chưa cấp, xem lịch sử và thống kê:

```bash
curl -X POST http://localhost:3000/api/access/check \
  -H 'Content-Type: application/json' \
  -d '{"uid":"DEADBEEF"}'
curl http://localhost:3000/api/logs
curl http://localhost:3000/api/stats
```

UID chưa đăng ký sẽ nhận `allowed: false`, `message: "từ chối"`; UID đang hoạt động sẽ nhận `allowed: true`, `message: "cho phép"`. Cả hai kết quả đều được ghi trong `access_logs`.

## Camera USB và YOLO

Cài AI riêng (có thể nặng, cần Internet lần đầu để tải weights):

```bash
python -m pip install -r ai/requirements.txt
```

Cắm webcam vào chính máy chạy FastAPI, đặt `CAMERA_INDEX=0` (hoặc `1` nếu cần), rồi mở dashboard cục bộ. Luồng annotate YOLO được cung cấp ở `/api/camera/stream.mjpg`. Để xem thử trực tiếp bằng cửa sổ OpenCV thay vì web:

```bash
python ai/run_camera.py
```

Nhấn `q` để thoát. Mô hình `yolov8n.pt` nhận diện class `person` và dùng **ByteTrack** (`model.track(..., persist=True, tracker="bytetrack.yaml")`) để gán ID theo dõi qua các khung hình. Hộp người sẽ hiển thị ID; khi một ID mới đi vào vùng cấm, hệ thống ghi sự kiện vào bộ nhớ và log server (tối đa 100 sự kiện gần nhất, cảnh báo được giới hạn để tránh spam). Đây là theo dõi đối tượng, không phải nhận diện danh tính người.

Vùng cấm được lưu trong `ai/zone.json` với tọa độ chuẩn hóa từ 0 đến 1. Nếu chưa có file, hệ thống dùng vùng mặc định. Để vẽ vùng bằng chuột, **dừng server FastAPI trước** rồi chạy `python ai/draw_zone.py`; click ít nhất 3 điểm, nhấn `S` để lưu, `C` để vẽ lại, `Q` để thoát. Đặt `CAMERA_INDEX=1` nếu webcam USB của bạn là camera số 1. API bổ sung: `GET /api/camera/zone`, `PUT /api/camera/zone` và `GET /api/camera/events`; `/api/camera/status` trả thêm `tracked_person_ids` và `last_intrusion_event`. Có thể đặt `KHOAI_YOLO_MODEL` để dùng file trọng số khác và `KHOAI_AI_DEVICE` để chọn thiết bị suy luận. Không có webcam hoặc thiếu thư viện AI thì dashboard báo camera ngoại tuyến, các chức năng API/web còn lại vẫn chạy.

## ESP32, RC522, servo, còi và ESP32-CAM

Xem [hướng dẫn đấu nối/nạp firmware](firmware/README.md). Trước khi nạp sketch ESP32 cần điền Wi‑Fi và IP LAN của máy chạy FastAPI. Mở cổng 3000 trên mạng nội bộ nếu firewall chặn kết nối. ESP32 và server phải cùng mạng, còn FastAPI cần lắng nghe trên `0.0.0.0`. Khi API không truy cập được, firmware fail-closed và không mở cửa.

**RC522 chỉ được cấp 3.3 V — tuyệt đối không nối vào 5 V.** Servo cần nguồn phù hợp riêng và chung GND với ESP32; không lấy nguồn servo từ chân 3V3. Kiểm tra sơ đồ, cực tính và dòng tiêu thụ trước khi cấp điện.

ESP32-CAM AI Thinker phát luồng tại `http://<IP-board>:81/stream`; trong giao diện vào **Thiết lập thiết bị**, nhập `http://<IP-board>:81` để lưu trên trình duyệt. Board và máy xem phải cùng LAN.

## Mô hình nhà kho nhỏ

Tham khảo [bản phác thảo mô hình và vị trí linh kiện](docs/mo-hinh-nha-kho.md) và [wireframe giao diện](docs/wireframe.md). Đây là bản vẽ/hướng dẫn, không phải mô hình vật lý đã lắp.

## Cấu trúc chính

- `backend/app/main.py`: API, SQLite, cấp quyền, lịch sử, stream camera.
- `frontend/`: trang camera, lịch sử, cấp thẻ và thiết lập camera.
- `ai/`: detector YOLO/OpenCV và chương trình xem webcam cục bộ.
- `firmware/`: sketch ESP32 + RC522 và ESP32-CAM.
- `docs/`: phác thảo UI và mô hình kho.
- `public/manus-routes.json`: danh sách route trang web cho Preview.

## Giới hạn an toàn

Đây chỉ là nguyên mẫu học tập trong mạng nội bộ: API hiện **không có đăng nhập/phân quyền, HTTPS, mã hóa UID, chống giả mạo thẻ hay cơ chế mở cửa an toàn được kiểm định**. Không công khai Internet, không dùng để bảo vệ kho thật, và không nhập dữ liệu cá nhân thật. SQLite cục bộ không phù hợp để lưu bền trên container triển khai có filesystem tạm; muốn dùng thật cần kiến trúc bảo mật, sao lưu, nguồn dự phòng và kiểm thử phần cứng chuyên nghiệp.
