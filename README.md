# KhoAI — Hệ thống giám sát và cảnh báo kho

**Phiên bản tài liệu:** v0.6.2-dev.24.66.8  
**Trạng thái:** prototype đang phát triển

KhoAI là dashboard giám sát kho kết hợp camera, AI phát hiện người, vùng bảo vệ, thẻ RFID và cảnh báo. Dự án hướng tới việc giúp người vận hành quan sát trạng thái kho và kiểm tra sự kiện trên một giao diện web.

> KhoAI chưa được kiểm định để dùng làm hệ thống an ninh duy nhất. Ngưỡng AI cần được đánh giá tại nơi lắp đặt; thiết bị thật và triển khai production cần được kiểm tra riêng.

## KhoAI hoạt động như thế nào?

1. **Camera USB** kết nối với máy chạy backend. OpenCV đọc hình ảnh; YOLO nhận diện người và ByteTrack theo dõi họ qua các khung hình.
2. **Decision Engine** đối chiếu vị trí người với vùng bảo vệ, trạng thái canh gác, quyền thẻ và thời gian hiện diện để xác định SAFE, WARNING hoặc ALARM.
3. **Backend FastAPI** quản lý tài khoản, thẻ, sự kiện, cảnh báo, bằng chứng và dữ liệu lịch sử trong SQLite.
4. **Dashboard web** hiển thị trạng thái, video, vùng bảo vệ, cảnh báo, sự cố và lịch sử để người vận hành kiểm tra.
5. **RFID/ESP32** có thể gửi UID thẻ đến API để kiểm tra quyền. Một lần quẹt thẻ không tự xác định người nào trong hình đã quẹt; việc liên kết thẻ với Track cần quy trình xác nhận.
6. **ESP32-CAM** có thể cung cấp luồng MJPEG để xem camera trong. Trong cấu hình hiện tại, luồng này không chạy pipeline nhận diện AI.

Các trạng thái và sự kiện hỗ trợ người vận hành ra quyết định; chúng không thay thế việc xác minh trực tiếp.

## Chức năng chính

- Dashboard web thích ứng với màn hình máy tính và điện thoại.
- Camera USB với pipeline OpenCV, YOLOv8 và ByteTrack.
- Vẽ vùng bảo vệ, theo dõi trạng thái camera/AI và lưu sự kiện.
- Quản lý thẻ RFID, hạn mức sử dụng, quyền truy cập và vé ghép tạm.
- Tài khoản admin/viewer, phiên đăng nhập và API có xác thực.
- Cảnh báo, nhật ký, bằng chứng hình ảnh và tích hợp Telegram tùy chọn.
- Công cụ Decision Engine replay để xem lại dữ liệu tọa độ/trạng thái Track.

## Công nghệ

- **Backend:** Python, FastAPI, SQLite.
- **AI và video:** OpenCV, Ultralytics YOLO, ByteTrack.
- **Frontend:** HTML, CSS, JavaScript ES Modules.
- **Thiết bị tùy chọn:** ESP32, RC522, servo, còi/LED và ESP32-CAM.
- **Triển khai:** chạy trực tiếp bằng Python hoặc Docker Compose.

## Cần cài gì?

### Chạy phần mềm

- Python **3.12** được khuyến nghị.
- Git để lấy mã nguồn.
- Camera USB nếu muốn chạy nhận diện video trực tiếp.
- Docker Desktop là tùy chọn nếu muốn chạy bằng Docker.

### Dùng firmware phần cứng

Arduino IDE và board ESP32 chỉ cần khi sử dụng thiết bị. Sketch RFID cần thư viện MFRC522, ArduinoJson 6/7 và ESP32Servo. Hướng dẫn đấu nối, nạp code và cấu hình nằm trong [firmware/README.md](firmware/README.md).

## Cài đặt và chạy trên Windows

Mở PowerShell tại thư mục gốc dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r ai/requirements.txt
Copy-Item .env.example .env
```

Mở file .env vừa tạo và thay các giá trị mẫu bằng secret riêng. Tối thiểu cần cấu hình:

- KHOAI_ADMIN_TOKEN: token quản trị ngẫu nhiên, tối thiểu 24 ký tự.
- KHOAI_API_KEY: API key ngẫu nhiên cho thiết bị, tối thiểu 32 ký tự, nếu dùng một key chung.
- KHOAI_BOOTSTRAP_ADMIN_USERNAME và KHOAI_BOOTSTRAP_ADMIN_PASSWORD: thông tin tạo admin ban đầu khi database chưa có tài khoản.

Không dùng nguyên giá trị mẫu, không commit .env, và không đưa mật khẩu Wi-Fi hoặc API key thật vào GitHub.

Khởi động ứng dụng:

```powershell
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 3000
```

Mở <http://127.0.0.1:3000> trên máy chạy backend. Camera USB phải được cắm vào máy đó. Có thể chạy python -m ai.list_cameras để kiểm tra index camera.

## Chạy bằng Docker

Sau khi tạo và cấu hình .env, chạy:

```powershell
docker compose up --build -d
```

Dashboard mặc định ở <http://127.0.0.1:3000>. Compose lưu database và dữ liệu runtime trong volume Docker. Việc truyền camera USB vào container phụ thuộc cấu hình Docker và hệ điều hành; không mặc định hoạt động trên mọi máy Windows.

## Bắt đầu sử dụng

1. Khởi động backend và đăng nhập bằng tài khoản admin bootstrap đã cấu hình.
2. Kết nối camera USB với máy chủ; xác nhận đúng camera trước khi bật nhận diện.
3. Trong dashboard, vẽ và lưu vùng bảo vệ theo hình ảnh camera cố định.
4. Kiểm tra trạng thái camera/AI và thử nghiệm trong môi trường an toàn trước khi bật canh gác.
5. Nếu dùng RFID, cấu hình key thiết bị ở backend và firmware. Chỉ kết quả API hợp lệ allow: true mới cho phép firmware mở servo.
6. Xem các sự kiện/cảnh báo và xác minh chúng với tình hình thực tế.

Camera trong ESP32-CAM có thể cấu hình qua KHOAI_ESP32_CAM_STREAM_URL, ví dụ http://<IP-ESP32-CAM>:81/stream.

## Cấu hình thiết bị RFID

API /api/rfid/scan yêu cầu X-API-Key. Có thể dùng KHOAI_API_KEY dùng chung hoặc cấu hình key riêng cho từng thiết bị bằng KHOAI_DEVICE_API_KEYS_JSON. Khi dùng registry riêng, ID phải khớp DEVICE_ID trong firmware; firmware gửi cả X-Device-ID và X-API-Key.

Ví dụ định dạng registry:

```dotenv
KHOAI_DEVICE_API_KEYS_JSON={"gate01":"THAY_BANG_SECRET_NGAU_NHIEN_IT_NHAT_32_KY_TU"}
```

Ví dụ trên chỉ minh họa định dạng; cần thay bằng secret thật. Firmware RFID mặc định dùng cổng 3000, ID gate01, và HTTP. Có thể bật HTTPS sau khi cài CA đáng tin cậy và cấu hình chứng thư hợp lệ. Nếu tiếp tục dùng HTTP, chỉ triển khai trên mạng thiết bị/VLAN cô lập vì API key không được mã hóa trên đường truyền.

MIFARE UID có thể bị sao chép trên một số loại thẻ/thiết bị. Nếu cần mức đảm bảo cao hơn, hãy dùng phần cứng và giao thức thẻ có xác thực mật mã.

## Cấu trúc mã nguồn

| Đường dẫn | Nội dung |
| --- | --- |
| backend/app/ | API, xác thực, database, route và dịch vụ |
| backend/app/telegram/ | Tích hợp Telegram |
| ai/ | Camera, detector, Decision Engine, homography và replay |
| frontend/ | Giao diện web và module frontend |
| firmware/ | Sketch ESP32 RFID và ESP32-CAM |
| config/profiles/ | Cấu hình profile demo/strict |
| tests/ | Test tự động |
| CHANGELOG_KHOAI.md | Lịch sử thay đổi |
| VERSION.txt | Phiên bản mã nguồn |

## Kiểm thử

Chạy bộ test Python từ thư mục gốc:

```powershell
python -m pytest -q
```

Báo cáo TEST_REPORT_v0.6.2-dev.24.66.8.txt ghi rõ rằng pytest, Docker build, Telegram thật, camera và ESP32 chưa được chạy lại sau thay đổi của phiên bản này. Vì vậy, không xem kết quả test của bản trước là kết quả xác minh cho bản hiện tại. Hãy chạy test và thử thiết bị trên staging trước khi phát hành.

## Giới hạn hiện tại

- Chất lượng nhận diện và các ngưỡng chưa được hiệu chuẩn bằng dữ liệu video tại kho triển khai.
- Camera, RFID, servo, còi, mạng LAN và hoạt động dài hạn cần kiểm tra trên đúng phần cứng.
- ID của tracker có thể thay đổi và không đại diện cho danh tính một người.
- RFID không tự chứng minh người trong hình là chủ thẻ.
- Không mở API, camera stream hoặc thiết bị trực tiếp ra Internet nếu chưa có lớp bảo vệ phù hợp.
- KhoAI là prototype hỗ trợ giám sát; cần người vận hành xác minh cảnh báo và duy trì biện pháp an ninh độc lập.

## Tài liệu liên quan

- [Hướng dẫn firmware](firmware/README.md)
- [Lịch sử thay đổi](CHANGELOG_KHOAI.md)
- [Báo cáo xác minh v0.6.2-dev.24.66.8](TEST_REPORT_v0.6.2-dev.24.66.8.txt)

