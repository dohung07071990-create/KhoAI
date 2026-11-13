KhoAI — Nguyên mẫu kiểm soát kho

**Phiên bản:** v0.6.2-dev.24.66.8  
**Trạng thái:** prototype đang phát triển

KhoAI là nguyên mẫu giám sát kho kết hợp FastAPI, SQLite, giao diện web, YOLO cho camera USB và firmware ESP32/RFID. Hệ thống giúp người vận hành theo dõi camera, vùng bảo vệ, thẻ, trạng thái SAFE/WARNING/ALARM và lịch sử sự kiện trên cùng một dashboard.

> Mã nguồn có firmware và hướng dẫn; phần cứng chưa được xác minh trên thiết bị thật trong bản phát hành này. Camera USB phải cắm vào máy chạy backend. ESP32 và máy chủ phải kết nối được với nhau qua mạng LAN. KhoAI chưa được kiểm định để dùng làm hệ thống an ninh duy nhất.

## Chạy server và web

Cần Python 3.12 (khuyến nghị) và Git. Từ thư mục gốc dự án:

```bash
python -m venv .venv

# Linux/macOS
source .venv/bin/activate

# Windows PowerShell
# .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r ai/requirements.txt

# Linux/macOS
cp .env.example .env

# Windows PowerShell: thay dòng trên bằng
# Copy-Item .env.example .env
```

Mở file .env và thay các giá trị mẫu bằng secret riêng:

- KHOAI_ADMIN_TOKEN: token quản trị ngẫu nhiên, tối thiểu 24 ký tự.
- KHOAI_API_KEY: API key thiết bị ngẫu nhiên, tối thiểu 32 ký tự.
- KHOAI_BOOTSTRAP_ADMIN_USERNAME và KHOAI_BOOTSTRAP_ADMIN_PASSWORD: tài khoản admin đầu tiên; đặt mật khẩu trước khi khởi động lần đầu.

Không dùng nguyên giá trị mẫu, không commit .env, mật khẩu, API key, database hoặc ảnh bằng chứng.

Khởi động backend:

```bash
python -m uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 3000
```

Mở http://localhost:3000. Cờ --reload phù hợp khi phát triển; bỏ cờ này khi chạy ổn định. Tài liệu API /docs bị tắt mặc định; chỉ bật trong môi trường phát triển bằng KHOAI_ENABLE_OPENAPI=1.

SQLite mặc định ở data/khoai.sqlite3; có thể đổi bằng DB_PATH. Múi giờ mặc định là Asia/Ho_Chi_Minh, cấu hình bằng BUSINESS_TIMEZONE.

## Thử API không cần mạch

Các API quản trị yêu cầu xác thực. Ví dụ PowerShell dưới đây dùng X-Admin-Token; thay giá trị bằng KHOAI_ADMIN_TOKEN trong .env:

```powershell
$h = @{ "X-Admin-Token" = "<KHOAI_ADMIN_TOKEN>" }
$card = @{ uid = "A1B2C3D4"; name = "Nhan vien demo"; daily_quota = 3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:3000/api/cards -Headers $h -ContentType "application/json" -Body $card

$check = @{ uid = "A1B2C3D4" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:3000/api/access/check -Headers $h -ContentType "application/json" -Body $check
Invoke-RestMethod -Uri http://localhost:3000/api/stats -Headers $h
```

Thẻ được cấp sẽ trả kết quả cho phép nếu còn hoạt động và chưa vượt hạn mức. UID chưa cấp, thẻ bị khóa, hết hạn hoặc hết quota sẽ bị từ chối. Các lần kiểm tra được ghi vào lịch sử. Có thể thử thêm từ dashboard sau khi đăng nhập admin.

## Camera USB và YOLO

Cài các gói AI ở bước trên, cắm camera vào chính máy chạy FastAPI rồi cấu hình CAMERA_INDEX trong .env (auto, 0, 1...). Dùng lệnh sau để dò camera:

```bash
python -m ai.list_cameras
```

Dashboard nhận luồng camera USB từ backend. YOLO dùng model pretrained yolov8n.pt để nhận diện người; lần chạy đầu có thể cần tải model từ Internet. Đây không phải model được huấn luyện riêng cho kho của bạn. Cần hiệu chuẩn vùng và đánh giá bằng video tại nơi lắp đặt; nếu thiếu camera hoặc AI, các chức năng web/API khác vẫn có thể chạy.

## RFID, ESP32 và ESP32-CAM

### ESP32 + RC522

Mở firmware/esp32_access/esp32_access.ino bằng Arduino IDE. Cài MFRC522, ArduinoJson 6/7 và ESP32Servo; điền Wi-Fi trong bản làm việc cục bộ, đặt IP server và cấu hình API key. Cổng mặc định là 3000, endpoint là /api/rfid/scan.

Firmware gửi X-API-Key và X-Device-ID. Key phải khớp cấu hình backend; chỉ phản hồi allow: true mới mở servo. Lỗi mạng/API hoặc key không hợp lệ giữ cửa đóng (fail-closed). HTTPS có hỗ trợ xác minh CA nhưng tắt mặc định; HTTP chỉ nên chạy trong mạng thiết bị cô lập.

RC522 dùng nguồn 3.3 V, không nối 5 V. Servo cần nguồn phù hợp riêng và nối chung GND với ESP32. Xem sơ đồ chân và hướng dẫn nạp trong firmware/README.md.

### ESP32-CAM

Sketch firmware/esp32_cam/esp32_cam.ino dành cho ESP32-CAM AI Thinker. Luồng MJPEG thường ở http://<IP-board>:81/stream. Đặt KHOAI_ESP32_CAM_STREAM_URL trong .env để backend cung cấp camera trong trên dashboard. Luồng này chỉ để xem, không tham gia nhận diện YOLO trong cấu hình hiện tại.

## Dự án xử lý sự kiện ra sao?

1. Camera USB gửi khung hình tới pipeline OpenCV.
2. YOLO nhận diện người; ByteTrack duy trì ID theo dõi tạm thời.
3. Decision Engine so vị trí với vùng bảo vệ, trạng thái canh gác và quyền đã cấu hình.
4. Backend ghi sự kiện/cảnh báo vào SQLite và chuyển trạng thái lên dashboard.
5. Người vận hành xem lại và xác minh cảnh báo. RFID không tự chứng minh người nào trong hình là chủ thẻ; việc ghép UID với Track cần thao tác rõ ràng.

## Cấu trúc chính

- backend/app/: API, xác thực, SQLite, route và dịch vụ.
- ai/: camera, detector, Decision Engine, homography và replay.
- frontend/: giao diện HTML/CSS/JavaScript.
- firmware/: ESP32 RFID và ESP32-CAM.
- config/profiles/: profile demo và strict.
- tests/: kiểm thử tự động.
- CHANGELOG_KHOAI.md: lịch sử thay đổi.
- TEST_REPORT_v0.6.2-dev.24.66.8.txt: trạng thái xác minh phiên bản này.

## Kiểm thử

Chạy từ thư mục gốc:

```bash
python -m pytest -q
```

Báo cáo phiên bản .8 ghi rõ pytest, Docker build, Telegram thật, camera và ESP32 chưa được chạy lại sau những thay đổi cuối. Kết quả của phiên bản trước không thay thế cho việc xác minh bản này.

## Giới hạn an toàn

KhoAI hiện là prototype, chưa được kiểm định để bảo vệ kho thật hoặc dùng làm hệ thống an ninh duy nhất. Chất lượng nhận diện, ngưỡng cảnh báo, camera, RFID, servo và hoạt động dài hạn cần được thử trên thiết bị và vị trí triển khai thực tế. UID của một số loại thẻ có thể bị sao chép. Không mở API hoặc luồng camera trực tiếp ra Internet; khi triển khai qua mạng, dùng HTTPS, firewall và phân đoạn mạng phù hợp.
