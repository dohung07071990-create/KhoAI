# KhoAI tích hợp — giao diện chính KHO.DOAN2

## Quyết định tích hợp
- Giao diện `frontend/index.html`, `frontend/app.js`, `frontend/style.css` lấy từ web KHO.DOAN2 đã chạy ổn định.
- Backend, AI, dữ liệu, API RFID/cảnh báo, cấu hình và firmware được giữ từ bản `KhoAI_integrated_full`.
- Thêm các API tương thích `/api/scans`, alias dữ liệu cảnh báo cho web KHO.DOAN2, và `DELETE /api/cards/{uid}`.
- Không ghi đè logic AI/firmware bằng mã giao diện.

## Chạy backend (Windows PowerShell)
Từ thư mục gốc chứa `backend`, `frontend`, `ai`, `firmware`:

```powershell
python -m pip install -r requirements.txt
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 3000
```

Mở `http://127.0.0.1:3000`. Nếu chạy từ thư mục `backend` thì dùng module path phù hợp với cấu trúc dự án, không chạy lệnh từ thư mục cha không chứa package `backend`.

## Lưu ý
- AI camera USB trên máy tính là tiến trình riêng của detector; camera ESP32-CAM trong kho vẫn là thiết bị riêng.
- Địa chỉ camera ngoài/trong được cấu hình trong giao diện KHO.DOAN2 như trước.
- Firmware cần trỏ về IP máy đang chạy backend và đúng cổng `/api/rfid/scan`; nếu bật `KHOAI_API_KEY`, firmware phải gửi cùng API key.
- Chưa thể xác nhận biên dịch firmware trên phần cứng thật chỉ bằng kiểm tra mã nguồn.

---

## Ghi chú từ README của bản KhoAI gốc

# KhoAI — AI giám sát và đối chiếu xuất kho (prototype)

> **Chú thích thay đổi:** các phần mới/sửa có nhãn `[NEW]` hoặc `[MODIFIED]` trong mã. Bản này giữ nền tảng FastAPI + SQLite + HTML/CSS/JS + YOLO + ByteTrack + firmware ESP32/RC522, không viết lại firmware không liên quan.

## 1. KhoAI hiện làm gì?

- **AI thị giác:** YOLO pretrained phát hiện người; ByteTrack duy trì `track_id` giữa các khung hình.
- **Vùng giám sát:** vùng đa giác được lưu trong `ai/zone.json`; người vào vùng khi chưa có thẻ được liên kết với ID camera sẽ tạo sự kiện.
- **Thời gian lưu lại:** nếu một ID ở trong vùng lâu hơn `KHOAI_DWELL_SECONDS`, tạo sự kiện `long_dwell` một lần cho lần hiện diện đó.
- **RFID:** API xác thực UID thẻ đã đăng ký. Để ghép thẻ với người trong video, cần gửi `track_id` rõ ràng hoặc dùng endpoint liên kết; quẹt thẻ tự nó không xác định được người nào trên hình.
- **Đối chiếu hàng hóa:** đăng ký SKU và số lượng được phép, sau đó so sánh với số lượng thực tế được nhập/cung cấp bởi tích hợp. Sai lệch tạo sự kiện an ninh được lưu trong SQLite.
- **Dashboard:** xem camera, lịch sử quẹt thẻ, thẻ được cấp, danh mục hàng và cảnh báo.

### Giới hạn quan trọng — không tuyên bố quá khả năng

Bản hiện tại **chưa tự đếm hàng hóa bằng AI**. API đối chiếu nhận `observed_quantity` từ người dùng hoặc hệ thống ngoài; muốn đếm tự động cần mô hình nhận diện hàng phù hợp với các SKU, dữ liệu kiểm thử và tích hợp kết quả đếm. `yolov8n.pt` mặc định được dùng cho người, không phải mô hình chuyên dụng cho mọi loại hàng trong kho.

Sự kiện vào vùng chưa liên kết thẻ được phát ra ngay khi ByteTrack thấy ID mới trong vùng. Nếu nhân viên phải quẹt thẻ sau khi bước vào, quy tắc này sẽ báo động trước khi quẹt; bố trí thực tế nên đặt vùng sau điểm quẹt thẻ hoặc đổi logic sang vùng đệm/thời gian ân hạn.

## 2. Chạy trên máy yếu (Windows)

Python 3.10+ được khuyến nghị. Trong thư mục gốc dự án:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r ai/requirements.txt
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 3000
```

Mở `http://127.0.0.1:3000`; tài liệu API ở `http://127.0.0.1:3000/docs`. Nếu PowerShell chặn activate, có thể chạy trực tiếp `\.venv\Scripts\python.exe -m pip ...` và `\.venv\Scripts\python.exe -m uvicorn ...`.

Lần chạy đầu YOLO có thể tải `yolov8n.pt`; cần Internet một lần hoặc đặt `KHOAI_YOLO_MODEL` tới file weights có sẵn. Camera USB phải cắm vào máy đang chạy FastAPI.

## 3. Cấu hình hiệu năng

Sao chép `.env.example` thành `.env` để tham khảo, sau đó khai báo biến môi trường trong terminal trước khi chạy (mã hiện chưa tự đọc file `.env`; có thể cài `python-dotenv` nếu muốn tự nạp file).

| Biến | Mặc định | Tác dụng |
|---|---:|---|
| `KHOAI_YOLO_MODEL` | `yolov8n.pt` | Dùng mô hình nano nhẹ, ưu tiên tốc độ CPU |
| `KHOAI_AI_DEVICE` | `cpu` | Chạy CPU, không yêu cầu GPU |
| `KHOAI_IMAGE_SIZE` | `640` | Giảm xuống `416` hoặc `320` nếu chậm; có thể giảm độ chính xác |
| `KHOAI_FRAME_WIDTH` / `HEIGHT` | `640` / `480` | Giảm kích thước hình đầu vào |
| `KHOAI_CONFIDENCE` | `0.35` | Ngưỡng phát hiện; tăng có thể giảm false positive nhưng bỏ sót nhiều hơn |
| `KHOAI_DWELL_SECONDS` | `30` | Thời gian lưu lại trước cảnh báo đứng lâu |
| `CAMERA_INDEX` | `0` | Chọn camera 0/1/2… |

**Tối ưu khuyến nghị:** bắt đầu với `yolov8n.pt`, 416 hoặc 320 px, camera 640×480, chỉ một luồng camera AI, không chạy mô hình nhận diện hàng hóa đồng thời. Nếu vẫn chậm, giảm độ phân giải camera; không nên tự giảm ngưỡng confidence quá thấp vì có thể tăng cảnh báo sai.

## 4. API mới và cách kiểm thử

### Đăng ký thẻ và xác thực

```bash
curl -X POST http://127.0.0.1:3000/api/cards -H "Content-Type: application/json" -d "{\"uid\":\"A1B2C3D4\",\"name\":\"Nhan vien demo\",\"age\":28}"
curl -X POST http://127.0.0.1:3000/api/access/check -H "Content-Type: application/json" -d "{\"uid\":\"A1B2C3D4\"}"
```

Nếu đã xác định được ID trên camera, có thể gửi `track_id` cùng payload `/api/access/check`, hoặc dùng endpoint dưới đây. Không tự động đoán ID người từ UID thẻ.

```bash
curl -X POST http://127.0.0.1:3000/api/access/associate -H "Content-Type: application/json" -d "{\"uid\":\"A1B2C3D4\",\"track_id\":1}"
```

### Đăng ký SKU và so sánh số lượng

```bash
curl -X PUT http://127.0.0.1:3000/api/inventory -H "Content-Type: application/json" -d "{\"sku\":\"BOX-001\",\"name\":\"Thung demo\",\"registered_quantity\":2}"
curl -X POST http://127.0.0.1:3000/api/inventory/compare -H "Content-Type: application/json" -d "{\"sku\":\"BOX-001\",\"observed_quantity\":3,\"track_id\":1}"
curl http://127.0.0.1:3000/api/security/events
```

Kết quả ví dụ sẽ là `matched: false`, `alert_to_security: true`, và ghi sự kiện sai lệch vào SQLite. Đây là phép thử đối chiếu nghiệp vụ, **không phải bằng chứng rằng camera đã tự đếm được 3 món**.

### API khác

- `GET /api/health`
- `GET /api/cards`, `POST /api/cards`
- `POST /api/access/check`, `POST /api/access/associate`, `GET /api/logs`
- `GET /api/stats`
- `GET /api/camera/status`, `GET /api/camera/zone`, `PUT /api/camera/zone`
- `GET /api/camera/events`, `GET /api/camera/stream.mjpg`
- `GET /api/inventory`, `PUT /api/inventory`, `POST /api/inventory/compare`
- `GET /api/security/events`

## 5. Vẽ vùng giám sát

Dừng server trước khi chạy công cụ vẽ để tránh hai tiến trình cùng mở camera:

```bash
python ai/draw_zone.py
```

Click ít nhất 3 điểm, nhấn `S` để lưu, `C` để vẽ lại, `Q` để thoát. Vùng lưu ở `ai/zone.json` với tọa độ chuẩn hóa 0–1. Nếu chưa có file, vùng mặc định được dùng.

## 6. Firmware ESP32 / RC522 / servo / còi / ESP32-CAM

Các sketch cũ được giữ nguyên. Xem `firmware/README.md` để cấu hình Wi-Fi và IP máy chạy FastAPI. RC522 chỉ cấp **3.3 V**; không nối chân nguồn RC522 vào 5 V. Servo cần nguồn phù hợp riêng và nối chung GND. Không thử trên cửa/kho thật khi chưa có kiểm thử an toàn.

## 7. Các thay đổi chính

- `[MODIFIED] ai/person_detector.py`: cấu hình nhẹ cho CPU, thời gian trong vùng theo từng `track_id`, sự kiện vào vùng chưa liên kết thẻ, cảnh báo đứng lâu, trạng thái liên kết thẻ, trạng thái camera không tự chạy inference khi dashboard chỉ hỏi status.
- `[MODIFIED] backend/app/main.py`: API liên kết thẻ–track, bảng inventory, API đối chiếu số lượng, lưu và truy xuất cảnh báo; SQLite WAL cho truy cập cục bộ.
- `[NEW] frontend`: trang “Hàng hóa & cảnh báo” để đăng ký SKU, so sánh số lượng và xem nhật ký sự kiện.
- `[MODIFIED] .env.example`: các tham số để giảm tải máy yếu.
- Firmware, sơ đồ và các phần UI khác được giữ nguyên để tránh phá vỡ tích hợp hiện tại.

## 8. Cải tiến có thể làm tiếp trên máy yếu

1. Ưu tiên nhận diện người bằng `yolov8n.pt`; chỉ chạy nhận diện hàng ở những thời điểm cần thiết, không phải mọi frame.
2. Chỉ chạy inference một lần và dùng chung frame/track cho mọi màn hình; hiện stream là nguồn kích hoạt xử lý camera.
3. Bổ sung hàng đợi sự kiện và thông báo Telegram/email nội bộ sau khi có cấu hình bảo mật.
4. Nếu cần đếm tự động, chọn 1–3 SKU rõ hình dạng, thu thập video kiểm thử và đánh giá trước khi fine-tune; không train mô hình “trộm cắp” chung chung ngay từ đầu.
5. Tích hợp RFID với `track_id` qua điểm quẹt có kiểm soát hoặc vùng đệm. Không coi một UID hợp lệ là bằng chứng rằng đúng người trong ảnh đã quẹt.

## 9. An toàn và giới hạn

Đây là nguyên mẫu học tập, không phải hệ thống an ninh đã được kiểm định. API chưa có đăng nhập/phân quyền, HTTPS, chống giả mạo thẻ hay cơ chế mở cửa an toàn. Không công khai Internet và không dùng dữ liệu cá nhân thật. Cảnh báo AI có thể sai; cần người bảo vệ xác minh trước khi hành động.


## Camera USB & vùng cấm (v0.3.0)
1. Cắm camera, chạy `python -m ai.list_cameras` (tắt server trước) -> xem ảnh trong `ai/camera_probe/` để biết index.
2. Đặt `CAMERA_INDEX=auto` (mặc định) hoặc số index trong `.env` (file `.env` giờ được đọc thật).
3. Chạy server, mở `http://127.0.0.1:3000`; trạng thái và lỗi camera hiện ngay trên khung camera.
4. Vẽ vùng cấm khi server đang chạy: `python -m ai.draw_zone --server http://127.0.0.1:3000` (S = lưu). Vẽ theo MẶT SÀN.
5. Báo đỏ sai? Thử `KHOAI_ZONE_MODE=overlap` hoặc `center`, chỉnh `KHOAI_ENTER_FRAMES` / `KHOAI_EXIT_FRAMES`.


## 5. Tích hợp chọn lọc từ KHO.DOAN2

Các phần tương thích đã được thêm mà không thay thế kiến trúc chính KhoAI:

- RFID: `POST /api/rfid/scan` là adapter cho firmware cũ; vẫn dùng logic kiểm tra thẻ của KhoAI.
- Hạn mức/ngày hết hạn/màu thẻ: các trường mới trên thẻ có mặc định tương thích dữ liệu cũ; dữ liệu hiện có không bị xóa.
- Quyền theo vùng và đơn lấy hàng: lưu thông tin qua `POST /api/cards` với các trường tùy chọn `zones`, `item`, `boxes`.
- Thiết bị: `POST /api/device/heartbeat`; trạng thái tổng hợp tại `GET /api/status`.
- Cảnh báo: `GET /api/alerts`, `POST /api/alerts/{event_id}/ack`.
- Camera OpenCV theo màu: `tools/color_detect.py` gửi sự kiện tới `POST /api/events`. Đây là bộ phát hiện màu thử nghiệm, không thay thế YOLO/ByteTrack và cần hiệu chỉnh HSV theo điều kiện camera thực tế.

Các API cũ của KhoAI, giao diện chính, hệ thống YOLO/ByteTrack, so sánh tồn kho và firmware hiện có được giữ lại. Phần giao diện KhoAI chưa được viết lại để hiển thị tất cả trường mới; có thể sử dụng API qua `/docs`.


## Tích hợp firmware ESP32 và giao diện mở rộng (2026-10-30)

- `firmware/esp32_access/esp32_access.ino`: RFID RC522 + servo + còi + LED, gọi `POST /api/rfid/scan`; mặc định server port `3000` theo cấu hình KhoAI. Nếu bạn chạy server ở cổng khác, sửa `SERVER_PORT`.
- `firmware/esp32_cam/esp32_cam.ino`: AI Thinker ESP32-CAM cung cấp `/capture` và `http://<IP>:81/stream`; nhập URL gốc của board ở mục Thiết lập thiết bị trên web.
- Trang Thẻ được cấp hiện hỗ trợ ngày hết hạn, hạn mức mỗi ngày, màu, quyền vùng, đơn hàng/số thùng và điền UID bị từ chối gần nhất. Trang Hàng hóa & cảnh báo có nút xác nhận xử lý cảnh báo.
- Điền Wi-Fi vào hai sketch trước khi nạp. Không dùng thông tin Wi-Fi mặc định/placeholder. Nếu muốn bảo vệ API RFID bằng key, đặt biến môi trường `KHOAI_API_KEY` trên máy chạy KhoAI và nhập cùng giá trị vào Serial Monitor bằng `key <chuoi_key>`. Nếu không đặt biến này, endpoint RFID không bắt buộc key.
- Camera ESP32-CAM và trình duyệt cần truy cập được cùng mạng LAN. Video MJPEG được tải trực tiếp từ board; backend YOLO/ByteTrack USB vẫn hoạt động độc lập.

Kiểm thử đã thực hiện ở mức cú pháp Python/JS và kiểm tra API bằng test cục bộ; chưa nạp firmware lên phần cứng thực tế.
