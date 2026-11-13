# KhoAI v0.6.2-dev.24.66.8 — Red-Team Robustness Fixes

Bản này xử lý các phát hiện độ bền từ bộ red-team: xác thực dữ liệu cho Decision Engine, chuẩn hóa UID tại detector, giới hạn hàng đợi vé RFID và kiểm tra ID Telegram ACK. Đây là hardening đầu vào; không thay đổi chính sách quyền truy cập hoặc thời gian grace của chống trộm.

- Kiến trúc backend và các thay đổi theo phiên bản: `CHANGELOG_KHOAI.md`.
- Báo cáo xác minh của bản này: `TEST_REPORT_v0.6.2-dev.24.66.8.txt`; pytest chưa được chạy lại sau các thay đổi.
- Hướng dẫn cài đặt, cấu hình và vận hành bên dưới vẫn áp dụng; các ghi chú lịch sử được giữ lại để tra cứu.

> **v0.6.2-dev.18:** dashboard bootstrap chạy dưới dạng ES Module; shared constants/state/event bus được tách vào `frontend/core/`. Bổ sung thư viện Homography XY (mặc định chưa hiệu chuẩn) và endpoint WebRTC thử nghiệm song song với MJPEG. Chưa có điểm đo thực tế nên không hiển thị tọa độ Track trên 3D; WebRTC chưa có client UI bật sẵn và chưa đo trên camera thật. Xem CHANGELOG_KHOAI.md.

> **v0.6.2-dev.17:** bổ sung tương tác chọn từng phòng/vùng giám sát trong mô hình 3D, bảng thông tin có thể đóng, hiệu ứng nhấn mạnh ALARM và giữ nguyên nguyên tắc không giả lập tọa độ người/Track theo phòng. Kế thừa kiểm tra fallback và sửa giao diện ở dev.16. Các thay đổi mới cần kiểm thử trình duyệt thực tế trước khi xác nhận tương tác WebGL.
> **v0.6.2-dev.16:** sửa chồng lấn chú giải/hướng dẫn trong khung 3D; kiểm tra đường fallback 2D bằng Chromium khi chủ động chặn import Three.js; loại ảnh kiểm thử khỏi ZIP phát hành; bổ sung giải thích vai trò dự phòng của `raw_inside` trong Decision Engine. Bố cục và fallback đã được kiểm tra bằng trình duyệt với JavaScript bật, nhưng backend thật, đăng nhập Viewer, polling dữ liệu thực và camera USB/YOLO chưa được kiểm chứng. Ngưỡng AI vẫn cần hiệu chuẩn bằng camera thật. Xem `CHANGELOG_KHOAI.md` và `TEST_REPORT_v0.6.2-dev.16.txt`.


### dev.16 — Twin UI verification
- Fixed overlap between the 3D status legend and the interaction/footer labels.
- Verified the JavaScript-driven 2D fallback in Chromium with the Three.js CDN import blocked.
- Release ZIP excludes browser validation screenshots; captures are retained separately.
- Documented the exceptional Engine-side `raw_inside` handover fallback.

# KhoAI v0.6.2-dev.17 — Interactive Digital Twin


## Cấu trúc backend (dev.24.64)

Backend đang được tách theo từng phần nhỏ để tránh thay đổi hành vi của hệ thống trong một lần đại tu:

- `backend/app/main.py`: composition root hiện tại, đăng ký FastAPI routes/lifespan và giữ các wrapper tương thích.
- `backend/app/settings.py`: đường dẫn và cấu hình runtime lấy từ environment.
- `backend/app/database.py`: mở kết nối SQLite, WAL, busy timeout và context manager transaction.
- `backend/app/schemas.py`: Pydantic request models và validation.
- `backend/app/retention.py`: retention service cho log, incident và evidence.
- `backend/app/telegram/`: tích hợp Telegram độc lập.
- `backend/app/stream_manager.py`, `backend/app/webrtc.py`: quản lý luồng camera và WebRTC.

`main.py` vẫn còn các route và nghiệp vụ liên kết chặt với trạng thái ứng dụng. Không nên chuyển hàng loạt route chỉ để giảm số dòng; các nhóm auth, camera, RFID, incidents và admin cần được tách theo từng đợt, có kiểm thử API tương ứng và giữ nguyên contract.

## Quy chuẩn giao diện (được kế thừa từ dev.24.7)

- Dùng system font stack, không phụ thuộc font ngoài chưa được đóng gói.
- Không dùng cỡ chữ 7–9px cho nội dung UI; nhãn phụ tối thiểu 11px.
- Điều hướng dùng SVG inline thay cho ký tự Unicode phụ thuộc hệ điều hành.
- Nút điều hướng và thao tác chính có chiều cao tối thiểu 44px.
- Giữ nguyên HTML/Vanilla JS/ES Modules và API backend; đợt này không chuyển frontend sang React.

## 1. Phạm vi hiện tại

- Camera USB bên ngoài có pipeline AI YOLO/ByteTrack và vùng bảo vệ.
- Camera trong ESP32-CAM có tab xem MJPEG trực tiếp, không tham gia xử lý AI trong phiên bản này.
- Luồng AI: OpenCV → YOLOv8n (person) → ByteTrack → Foot Point → Decision Engine → Alarm/Event/Evidence.
- Từ v0.6.0, `ai/decision.py` là nguồn quyết định trạng thái sống SAFE/WARNING/ALARM; backend không suy ra trạng thái sống từ các sự kiện lịch sử trong SQLite.
- Thẻ chỉ miễn báo động xâm nhập nếu quyền của thẻ chứa đúng `KHOAI_CAMERA_ZONE_ID`; mặc định là `external_usb_zone`.
- Người lạ vào vùng có thời gian chờ `KHOAI_ENTRY_GRACE_SECONDS` (mặc định 8 giây trong cấu hình demo); người đã ở trong vùng trước khi bật chống trộm bị đánh giá ngay.
- Sau khi xác nhận rời vùng, `session_id` và trạng thái WARNING/ALARM được giữ trong `KHOAI_PRESENCE_RELEASE_SECONDS` (mặc định 8 giây). Nếu quay lại trước khi cửa sổ này hết, phiên cũ tiếp tục; chỉ khi hết cửa sổ mới đóng phiên và phát `intrusion_attempt_aborted` (nếu phiên chưa từng ALARM và đủ thời lượng). Bộ đếm ân hạn tiếp tục trong giai đoạn xác nhận rời, nhưng tạm dừng sau khi rời được xác nhận. Nếu Track thuộc phiên WARNING biến mất quá `KHOAI_TRACK_HOLD_SECONDS` trước khi hết cửa sổ release, engine đóng phiên và phát `intrusion_attempt_aborted` đúng một lần nếu thời lượng bên trong đạt ít nhất 5 giây. Track ALARM không bị đổi thành sự kiện aborted.
- ByteTrack ID chỉ có ý nghĩa trong một luồng camera; không phải danh tính. Khi ID đổi, Decision Engine chỉ xét ghép vị trí một-một trong cùng vùng và cửa sổ mặc định 3,5 giây (`KHOAI_HANDOVER_MAX_GAP_SECONDS`). Nếu Track mới `inside=True`, phiên xâm nhập có thể được tiếp tục ngay. Nếu `inside=False` nhưng `raw_inside=True`, Engine dùng ngưỡng dự phòng 0,22 giây liên tục trước khi cho phép kế thừa phiên (có thể chỉnh bằng `KHOAI_HANDOVER_RAW_INSIDE_CONFIRM_SECONDS`). Với pipeline detector mặc định, `ENTER_CONFIRM_SECONDS` (0,10 giây) thường xác nhận `inside=True` trước, nên nhánh raw-inside chủ yếu dành cho adapter detector tùy chỉnh, dữ liệu replay hoặc trường hợp cờ `inside` đến trễ/mất; một lần chạm ranh giới ngắn hơn ngưỡng không đủ. Nếu Track mới chỉ `warning=True` trong vùng đệm và không có raw-inside đang chờ xác nhận, chỉ bộ đếm proximity được chuyển, không chuyển `session_id`, `entered_at`, bộ đếm xâm nhập hay trạng thái ALARM. Handover vẫn có thể ghép nhầm người khác xuất hiện gần vị trí cũ; che khuất giữa khung rồi xuất hiện người khác đúng vị trí trong 3,5 giây vẫn có thể kế thừa bộ đếm proximity. Nếu mất Track quá 3,5 giây, không còn continuity handover. Không có trí nhớ theo vùng.
- Luật rời khung dùng lịch sử bbox từ trước dải mép. Trái/phải dùng tâm khung người để không bị cạnh dẫn đầu bị cắt làm đứng yên; mép trên dùng tâm khung; mép dưới dùng lịch sử chân còn nhìn thấy và chuyển sang cạnh trên bbox khi chân đã bị cắt. Các ngưỡng mẫu, thời gian lịch sử, khoảng thời gian tối thiểu và vận tốc hướng ra đều cấu hình được qua `KHOAI_HANDOVER_EDGE_*`. Thiếu mẫu, đứng yên hoặc đi dọc mép thì cho phép handover. Người ra rất chậm vẫn có thể được cho phép handover nếu lịch sử hợp lệ không đủ; cần kiểm chứng với camera thật.
- RFID ticket chỉ tự ghép khi có ROI cửa được lưu từ giao diện, đúng một vé và đúng một Track trong ROI. Nhiều người hoặc nhiều vé thì không tự ghép; quản trị viên chọn UID và Track trên web, có ảnh cắt trực tiếp từ camera. Thẻ mới được cấp mặc định có quyền Camera USB ngoài; có thể bỏ chọn quyền này. Nếu thiếu quyền, API RFID trả rõ `Thẻ chưa có quyền Camera USB ngoài.`
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

Mở `http://127.0.0.1:3000`. Nếu chưa có file `.env`, hãy sao chép `.env.example` thành `.env`, thay `KHOAI_ADMIN_TOKEN` bằng chuỗi bí mật riêng và khởi động lại backend. Không dùng nguyên giá trị mẫu khi triển khai thực tế. Khi dùng cơ chế token dùng chung, trình duyệt gửi `KHOAI_ADMIN_TOKEN` qua header để nhận cookie session `HttpOnly` (8 giờ). Với tài khoản cá nhân, đăng nhập bằng username/password. Cookie session chỉ được lưu dưới dạng SHA-256 trong SQLite; giá trị cookie nguyên bản không được ghi vào database hoặc audit log. Frontend không lưu admin token trong `sessionStorage` hoặc `localStorage`; stream/ảnh dùng cookie phiên, không đưa token vào URL.

`KHOAI_ADMIN_TOKEN` phải là secret riêng dài ít nhất 24 ký tự; giá trị mẫu hoặc ngắn hơn bị từ chối khi khởi động. Sau lần nhập đầu tiên, backend cấp session ID ngẫu nhiên trong cookie HttpOnly; session hết hạn phía server sau 8 giờ mặc định. Frontend không lưu admin token trong Web Storage. Khi triển khai qua LAN, dùng HTTPS reverse proxy. Lần chạy YOLO đầu tiên có thể cần tải `yolov8n.pt`; nếu tải thất bại, worker tự retry theo backoff. Camera USB phải được cắm vào máy đang chạy backend. Dùng `python -m ai.list_cameras` để kiểm tra index camera.

## 3. Bảo mật API — bắt buộc cấu hình

- API xác thực bằng session cookie HttpOnly có hạn phía server hoặc header `X-Admin-Token` để đổi session. Query-string token bị vô hiệu hóa.
- `viewer` chỉ được đọc dữ liệu vận hành (dashboard, camera, sự kiện an ninh, lịch sử quẹt thẻ, cảnh báo và incident). Nhật ký truy cập hệ thống, danh sách tài khoản, cấu hình và mọi thao tác ghi chỉ dành cho `admin`.
- Quyền hiện tại được đọc từ `admin_users` ở mỗi request; middleware không quyết định quyền. Lỗi DB khi xác thực session/role trả HTTP 503 (fail-closed).
- Session ID chỉ được lưu dạng SHA-256 trong `admin_sessions`; audit log chỉ lưu digest rút gọn và API lịch sử không trả trường session. Migration bảo mật đầu tiên vô hiệu hóa toàn bộ session cũ và xóa session ID cũ khỏi nhật ký; mọi người dùng phải đăng nhập lại sau khi nâng cấp.
- Đổi role, đổi mật khẩu hoặc vô hiệu hóa tài khoản sẽ thu hồi session hiện có của tài khoản đó.
- `POST /api/rfid/scan` và `POST /api/device/heartbeat` luôn yêu cầu `X-API-Key` khớp `KHOAI_API_KEY`. Nếu chưa đặt key, endpoint thiết bị bị khóa; không còn chế độ bỏ qua key.
- `/api/health` là endpoint liveness/health công khai; các API dữ liệu và media yêu cầu admin. Không mở cổng trực tiếp ra Internet; dùng firewall/VPN và HTTPS reverse proxy nếu truy cập từ xa. Cookie session trên HTTP LAN không được mã hóa.
- Không dùng UID thẻ MIFARE Classic làm xác thực mật mã mạnh: UID có thể bị sao chép trên một số loại thẻ/thiết bị. Đây là giới hạn của prototype.

Ví dụ tạo thẻ (PowerShell):

```powershell
$h = @{ "X-Admin-Token" = $env:KHOAI_ADMIN_TOKEN }
$b = @{ uid="A1B2C3D4"; name="Nhan vien demo"; daily_quota=3 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:3000/api/cards -Headers $h -ContentType "application/json" -Body $b
```

Ví dụ ESP32 gọi RFID phải gửi `X-API-Key: <KHOAI_API_KEY>`; firmware cần được cấu hình cùng giá trị. Không ghi key thật vào README hoặc Git.


### Decision Engine record/replay (tùy chọn)

Mặc định tắt. Để ghi đầu vào tại ranh giới `evaluate()`, đặt `KHOAI_DECISION_RECORD_ENABLED=1`. Mỗi phiên có một dòng đầu trang chứa snapshot `DecisionConfig`; các frame sau ghi `session_id`, số thứ tự frame, timestamp, kích thước frame, `observations`, trạng thái armed, đồng hồ engine, health inputs và kết quả sự kiện/trạng thái. Observation chứa ID, bbox, footpoint, inside/warning, `exit_boundary_inside`, cờ rời khung và quyền thẻ. Chỉ lưu tọa độ/trạng thái Track, không lưu ảnh và không ghi vào SQLite.

Giới hạn mặc định: 20 MiB cho file hoạt động, tối đa một file xoay `.1` và 7 ngày lưu. Khi file hoạt động đầy, file cũ được xoay và ghi tiếp; bản `.1` cũ bị thay thế. Khi replay, công cụ đọc file `.1` trước rồi đến file hiện tại, reset Engine tại mỗi `session_start`.

```powershell
python -m ai.decision_replay data/decision_replay.jsonl
python -m ai.decision_replay data/decision_replay.jsonl --set entry_grace_seconds=20
```

Replay dùng đồng hồ giả từ trường `now`, không khởi động camera/backend/CSDL. `--set` chạy lại với cấu hình mới và **vẫn so sánh** sự kiện/trạng thái với kết quả đã ghi; đầu ra liệt kê frame có khác biệt. Đây là công cụ đánh giá tác động ngưỡng, không tự hiệu chuẩn ngưỡng.

### Cấu hình Demo/Strict

`KHOAI_PROFILE=demo` (mặc định) hoặc `KHOAI_PROFILE=strict` chọn các giá trị khởi đầu trong `config/profiles/*.json`. Demo: ân hạn vào 8 giây, release 8 giây, vé RFID 20 giây, SUSPICIOUS 30 giây/3 lần tiếp cận, handover gap 3,5 giây và bán kính ghép 0,08. Strict: 5 giây, 15 giây, 10 giây, SUSPICIOUS 20 giây/2 lần, handover gap 2,5 giây, bán kính 0,05 và bán kính loại trừ mơ hồ 0,10. Biến môi trường tương ứng nếu được khai báo sẽ ghi đè profile. Đây là giá trị khởi đầu, **chưa được hiệu chuẩn** bằng camera thực. Không gia hạn ân hạn theo vé RFID trong dev.13; việc này được bỏ để tránh kéo dài cơ hội bám đuôi, thay vào đó dùng ROI cửa và ghép thủ công khi mơ hồ. Vùng bảo vệ và ROI cửa được vẽ/lưu trên web; các ngưỡng còn lại là cấu hình nâng cao qua profile hoặc environment.

## 4. Các API đang có

### Camera trong ESP32-CAM

- Cấu hình `KHOAI_ESP32_CAM_STREAM_URL=http://<IP-ESP32-CAM>:81/stream` trong `.env`, khởi động lại backend, sau đó mở tab **Camera trong**. Trình duyệt chỉ truy cập endpoint proxy có xác thực của backend.
- Firmware `firmware/esp32_cam/esp32_cam.ino` cung cấp MJPEG tại cổng 81, đường dẫn `/stream`.
- Camera trong truyền trực tiếp từ trình duyệt; không phụ thuộc token quản trị backend và không đi qua YOLO.

### Camera USB ngoài

- `GET /api/camera/status`
- `GET /api/camera/stream` — MJPEG stream
- `GET /api/camera/snapshot` — JPEG snapshot
- `GET /api/camera/zone`, `PUT /api/camera/zone`
- `GET /api/rfid/entry-roi`, `PUT /api/rfid/entry-roi` — ROI cửa RFID được lưu trên máy chủ; đa giác tự cắt hoặc diện tích bằng 0 bị từ chối.
- `POST /api/incidents/siren-off` — tắt còi đang hoạt động, độc lập với ACK và trạng thái incident.
- `GET /api/rfid/pending` — vé đang chờ và Track hiện diện; ảnh Track qua `/api/camera/tracks/{track_id}/thumbnail`
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
3. Lưu vùng. Tọa độ được lưu chuẩn hóa trong `ai/zone.json`. Trong v0.6.0, đa giác camera USB này có định danh cấu hình `KHOAI_CAMERA_ZONE_ID` (mặc định `external_usb_zone`); khi tạo thẻ, cấp quyền vùng “Camera USB ngoài” để thẻ được miễn báo động xâm nhập tại vùng này.
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

Worker nền tự dọn `access_logs` và `security_events` quá thời hạn `KHOAI_LOG_RETENTION_DAYS` (mặc định 365 ngày); đặt `0` hoặc số âm để tắt. Ảnh bằng chứng được dọn theo tuổi/dung lượng; khi ảnh bị xóa, URL trong metadata sự kiện được xóa và đánh dấu `evidence_expired`. Ảnh được tham chiếu bởi incident đang OPEN được bảo vệ. Sao lưu DB trước khi thay đổi chính sách lưu trữ.


## v0.5.2 – hardening follow-up

- Các API đọc dữ liệu nhạy cảm (UID, log, lượt quẹt, cảnh báo, trạng thái camera) yêu cầu `X-Admin-Token`.
- Luồng/ảnh camera dùng tham số `token` vì thẻ `<img>` không gửi được header tùy chỉnh. Token trên URL có thể xuất hiện trong browser history/access log; chỉ dùng trong LAN demo, không triển khai Internet theo cấu hình này.
- `tools/color_detect.py` cần biến môi trường `KHOAI_ADMIN_TOKEN` giống backend.
- Docker mặc định không ánh xạ webcam. Trên Linux có webcam `/dev/video0`, chạy thêm `docker compose -f docker-compose.yml -f docker-compose.linux-camera.yml up --build`. Docker Desktop trên Windows không hỗ trợ ánh xạ webcam USB theo cách `/dev/video0`; chạy camera/backend trực tiếp trên Windows hoặc dùng Linux host.
- Token dùng chung qua HTTP chỉ phù hợp demo LAN tin cậy; triển khai thực tế cần HTTPS, rate limiting, quản lý token riêng và kiểm soát mạng.


### Kiểm thử và tài liệu API (mốc lịch sử v0.5.4)
- Cài thư viện kiểm thử bằng `pip install -r requirements-dev.txt`; image Docker production chỉ cài `requirements.txt`.
- `/docs`, `/redoc` và `/openapi.json` tắt mặc định. Chỉ bật trong môi trường phát triển bằng `KHOAI_ENABLE_OPENAPI=1`.
- Công cụ vẽ vùng khi server chạy: `python -m ai.draw_zone --server http://127.0.0.1:3000 --token "$env:KHOAI_ADMIN_TOKEN"` (PowerShell), hoặc đặt biến môi trường `KHOAI_ADMIN_TOKEN`. Token được gửi bằng header, không gắn vào URL.


### Kiểm thử xác thực frontend (mốc lịch sử v0.5.4)

Chạy kiểm thử JavaScript bằng Node.js (không cần thư viện npm):

```bash
node --test tests/test_frontend_auth.js
```

Kiểm thử backend dùng `pip install -r requirements-dev.txt` rồi `python -m pytest -q`.

## 9. Decision Engine v0.6.0

- `ai/decision.py` không phụ thuộc OpenCV, YOLO, database hoặc đồng hồ hệ thống; caller truyền `now` dạng monotonic để test xác định.
- `KHOAI_ENTRY_GRACE_SECONDS=15`: thời gian chờ mặc định cho người chưa có quyền.
- `KHOAI_WRONG_ZONE_GRACE_SECONDS=15`: thời gian trước khi người có thẻ nhưng không có quyền tại vùng hiện tại chuyển sang ALARM.
- `KHOAI_DWELL_REVIEW_SECONDS=300`: ngưỡng đứng lâu để chuyển người đã được cấp quyền sang REVIEW (không phải ALARM).
- `KHOAI_CAMERA_ZONE_ID=external_usb_zone`: tên vùng duy nhất gắn với đa giác USB hiện tại.
- `POST /api/alerts/{id}/ack` chỉ xác nhận bản ghi lịch sử; trạng thái sống vẫn do camera/Decision Engine quyết định.

**Giới hạn v0.6.0:** cấu hình hình học vẫn chỉ có một đa giác; chưa có mapping cửa–vùng, vé RFID tạm, ghép thẻ tự động, bàn giao quyền giữa track ID, hoặc gửi Telegram bất đồng bộ. Các mục này không được xem là đã hoàn thành trong bản phát hành này.

## 10. Reliability & Health v0.6.1 (bản vá v0.6.1.1)

- Watchdog độc lập kiểm tra mỗi giây; `camera_ok` dựa trên tuổi frame chụp, `ai_ok` dựa trên model đã nạp và tuổi frame đã xử lý.
- Khi hệ thống đã qua `KHOAI_STARTUP_GRACE_SECONDS` (60 giây mặc định), camera/AI lỗi sẽ tạo WARNING và leo thang ALARM sau `KHOAI_HEALTH_ESCALATION_SECONDS` (30 giây mặc định) nếu chống trộm đang bật.
- Camera cần duy trì khoảng **3 FPS trở lên** để đáp ứng ngưỡng ổn định hiện tại (frame gap tối đa 0,5 giây); 2 FPS danh nghĩa không được xem là đủ vì jitter có thể làm gap vượt ngưỡng.
- Mất ổn định cadence camera chỉ phát cảnh báo sau `KHOAI_CAMERA_UNSTABLE_DELAY_SECONDS` (mặc định 3,5 giây, luôn được giới hạn nhỏ hơn mốc leo thang health); thời gian leo thang ALARM vẫn tính từ lần đầu phát hiện lỗi. Điều kiện fail-closed của RFID không có debounce và chặn ngay khi camera không ổn định.
- Khi cadence thấp kéo dài, log server ghi capture FPS và frame gap lớn nhất quan sát được để hỗ trợ phát hiện cấu hình camera không phù hợp.
- `KHOAI_TRACK_HOLD_SECONDS=5` chỉ giữ ngữ cảnh Track phục vụ hysteresis/Decision Engine, không giữ quyền RFID. Quyền RFID bị thu hồi nếu Track không được xác nhận trong hơn 0,75 giây; giới hạn tuyệt đối `KHOAI_AUTH_MAX_SECONDS` mặc định và tối đa 60 giây. Ticket RFID tối đa 20 giây. Sau khi quyền hết hạn/thu hồi, cần quẹt thẻ và liên kết lại.
- Đồng hồ hiện diện theo vùng dùng `KHOAI_PRESENCE_RELEASE_SECONDS=30`; khoảng vắng ngắn chỉ tạm dừng, không reset. Reset tức thời chỉ xảy ra khi chính track chuyển từ WARNING/ALARM sang AUTHORIZED và không còn track chưa xác thực khác trong cùng vùng. Anonymous dùng `KHOAI_ANONYMOUS_DEBOUNCE_SECONDS=1`.
- API camera status có `camera_ok`, `ai_ok`, `tracking_enabled`, `alarm`, `latched`, `acknowledged`, `siren`, `incidents`. v0.6.2 bổ sung incident persistence và endpoint xác nhận incident.
- Đây là kiểm thử mô phỏng và kiểm thử phần mềm. Camera USB, model YOLO thật, firmware ESP32 và còi vật lý chưa được kiểm chứng.


### Bổ sung nghiệm thu v0.6.1 (sửa theo phản hồi tester)

- Đồng hồ ân hạn dùng occupancy tích lũy theo vùng; track ra/vào hoặc mất detection không xóa thời gian đã tích lũy.
- Việc xác thực một track chỉ reset đồng hồ khi track đó vừa chuyển từ WARNING/ALARM sang AUTHORIZED và không còn người chưa xác thực khác trong vùng.
- REVIEW là nhãn cần xem lại theo track, không nâng mức `alarm` tổng.
- Anonymous chỉ nâng mức tổng sau debounce và không được hạ mức ALARM của track có ID.
- Giới hạn ảnh bằng chứng: `KHOAI_EVIDENCE_INTERVAL_SECONDS` (mặc định 1 giây) tính theo file ảnh; mọi sự kiện phát sinh từ cùng một frame được gắn chung URL ảnh của frame đó. Frame bị giới hạn tần suất vẫn giữ nguyên sự kiện dù không tạo file ảnh mới.
- Track đã xác thực đúng vùng luôn SAFE trong các frame ở vùng cảnh báo mở rộng trước khi xác nhận vào đa giác hoặc sau khi ra khỏi đa giác; không phát `zone_warning`/WARNING giả cho nhân viên hợp lệ.
- Một ảnh JPEG được lưu tối đa một lần cho mỗi frame được chọn; `alarm_state_changed`, `unauthorized_entry` và các sự kiện khác từ cùng frame cùng trỏ tới một URL, tránh ảnh bị gắn riêng cho sai sự kiện.
- v0.6.2-dev.1 bổ sung bàn giao quyền bảo thủ khi ByteTrack đổi ID: track cũ và track mới phải khớp không gian, trong `KHOAI_TRACK_HOLD_SECONDS`, và không có track cạnh tranh. Đây là heuristic thị giác, không phải xác minh danh tính sinh trắc học.


### Phương pháp đo nghiệm thu

- Ghi mốc thời gian bắt đầu/kết thúc và nhãn sự kiện của từng kịch bản; chạy lặp nhiều lượt với cùng chuỗi đầu vào mô phỏng.
- Báo cáo trung bình và khoảng dao động cho FPS, độ trễ xử lý, độ trễ ALARM so với mốc 15 giây, số báo nhầm/giờ và số lần bỏ sót xâm nhập.
- `false alarms/hour` = số lần ALARM không có xâm nhập được gán nhãn chia cho tổng thời gian chạy theo giờ.
- `missed intrusions` = số lượt xâm nhập có nhãn nhưng không tạo ALARM trong ngưỡng nghiệm thu.
- `alarm latency error` = thời điểm ALARM thực tế trừ thời điểm ALARM kỳ vọng (15 giây tính theo thời gian hiện diện tích lũy).
- Báo cáo mô phỏng và kiểm thử camera/YOLO/firmware thực tế thành hai nhóm riêng; không suy diễn kết quả phần cứng từ mô phỏng.


## 11. v0.6.2-dev.1 — Incident, RFID và triển khai

- Incident được tạo khi có ALARM đầu tiên, gộp sự kiện theo incident/cooldown, lưu SQLite; acknowledgement là endpoint riêng `POST /api/incidents/{id}/ack`. Intrusion incident vẫn latch sau khi còi timeout; chỉ đóng khi đã xác nhận, chống trộm vẫn bật và Decision Engine trở về SAFE. Tắt chống trộm không được coi là bằng chứng vùng đã an toàn. ALARM mới trong incident đang mở sẽ reset acknowledgement và thời gian còi. Camera outage/AI health được ghi thành incident sức khỏe riêng và tự đóng khi phục hồi tương ứng.
- `KHOAI_SIREN_MAX_SECONDS` mặc định 60 giây. ACK không tắt còi. Quản trị viên có thể tắt còi riêng bằng `POST /api/incidents/siren-off` hoặc nút “Tắt còi” trên dashboard; thao tác này không ACK và không đóng incident. Firmware ESP32 chưa được nối với tín hiệu siren trong bản này.
- RFID scan hợp lệ và có quyền Camera USB tạo ticket dùng một lần (`KHOAI_RFID_TICKET_SECONDS`, tối đa 20 giây). ROI cửa được vẽ/lưu từ tab thẻ trên web. Tự ghép RFID **tắt mặc định** (`KHOAI_RFID_AUTO_BIND_ENABLED=0`) vì vị trí RC522 so với vùng nhìn camera chưa được xác minh; quản trị viên phải chọn Track hiển thị và liên kết thủ công. Chỉ bật tự ghép sau khi xác nhận đầu đọc nằm trong ROI và camera nhìn rõ người quẹt. Khi bật, hệ thống chụp tập ứng viên tại thời điểm quẹt; chỉ đúng một detection có Track ID mới được xét, và bất kỳ người mới/ứng viên thay đổi/mất detection trong cửa sổ ổn định đều chuyển sang xác nhận thủ công. Đây chỉ là tương quan không gian-thời gian, không phải xác minh danh tính.
- Hàng đợi vé chờ tối đa mặc định 1024 UID (`KHOAI_RFID_MAX_PENDING_TICKETS`); vé hết hạn được dọn khi thêm/đọc vé. Nếu đầy, API không tạo vé liên kết Track mới và trả thông báo trạng thái.
- Watchdog thu hồi ticket RFID và toàn bộ quyền Track khi tuổi frame đạt 3 giây, kể cả khi cờ camera health chưa chuyển sang offline. Đây là bảo đảm ở mức mã/watchdog; chưa xác nhận camera USB vật lý có trường hợp driver `cap.read()` bị chặn.
- Quyền RFID không được gia hạn trượt; hết thời hạn tuyệt đối (mặc định và tối đa 60 giây) phải quẹt/liên kết lại. Quyền bị thu hồi nếu Track mất dấu quá 0,75 giây (giữ nguyên ngưỡng, chưa hiệu chỉnh bằng camera thật) hoặc quỹ đạo giao cắt/chồng lấn mạnh (IoU ≥ 0,50) với Track khác. Grace Decision Engine giữ nguyên 8 giây; không thêm khoảng miễn trừ riêng cho trạng thái chưa xác thực.
- Không bàn giao quyền RFID chỉ dựa trên khoảng cách/IoU khi ByteTrack đổi ID. Track ID không phải danh tính; sau mất dấu hoặc giao cắt, cần xác thực lại.
- `PATCH /api/cards/{uid}` khóa/mở thẻ; khóa hoặc xóa thẻ gọi `detector.revoke_uid()` để thu hồi mọi track và ticket cùng UID.
- Ảnh bằng chứng bị giới hạn tần suất sẽ dùng URL ảnh gần nhất và ghi `evidence_reused`, `image_age_ms`, `evidence_timestamp`; frame ALARM có thể vượt cooldown để lưu ảnh mới. Không còn xóa ảnh theo quota số file chung; cần cấu hình dung lượng/retention cho triển khai dài hạn.
- Admin token chỉ dùng để đổi lấy session ID ngẫu nhiên lưu SQLite; cookie có hạn phía server (mặc định 8 giờ), frontend không lưu token trong sessionStorage. Rate limit mặc định 5 token sai/IP/60 giây. Token mẫu hoặc dưới 24 ký tự bị từ chối. Triển khai qua LAN cần HTTPS để tránh session cookie bị quan sát trên HTTP.
- YOLO tự retry tải model với backoff tối đa 60 giây. Ngưỡng vào/ra vùng chuyển từ số frame sang `KHOAI_ENTER_CONFIRM_SECONDS` và `KHOAI_EXIT_CONFIRM_SECONDS`.
- `camera_offline` chỉ do `_set_camera_health()` phát; watchdog không phát trùng. Health fault được truyền vào Decision Engine và escalation tạo `alarm_state_changed`.
- SQLite sync/retention worker chạy bằng `asyncio.to_thread`. Camera trong ESP32-CAM dùng backend proxy có xác thực; URL đặt ở `KHOAI_ESP32_CAM_STREAM_URL`, không hard-code IP ở frontend.
- Dashboard lấy số người trong vùng và thời gian track từ detector USB thay cho số liệu demo cũ. `/api/health` lấy version từ `VERSION.txt` và báo `camera_ok`/`ai_ok`.
- Docker dùng volume cho database/zone/evidence và weights (`/app/data/yolov8n.pt`), user không phải root và HEALTHCHECK HTTP. Đặt file weights vào volume để chạy offline; nếu chưa có, YOLO sẽ thử tải lại theo backoff. Docker image CPU torch và proxy stream chưa được build/kiểm thử trong môi trường Docker ở lần đóng gói này.

### Giới hạn lịch sử của dev.1 (đã được cập nhật ở dev.9)

- Dev.1 chưa có giao diện ROI cửa; dev.9 đã bổ sung ROI lưu trên máy chủ và manual binding. Việc ghép tự động vẫn là heuristic theo vị trí, không xác minh danh tính.
- Handover theo IoU/khoảng cách có thể ghép nhầm người nếu họ đứng sát nhau; cần hiệu chỉnh ROI, khoảng cách và kiểm thử thực địa. Chưa có so khớp màu áo.
- Ảnh bằng chứng hiện được giữ lại, chưa có retention theo incident/dung lượng; pre-roll chưa triển khai.
- Chưa có output siren vật lý, Telegram, điều khiển còi ESP32 hoặc xác minh camera/YOLO/firmware thật.
- `tools/color_detect.py` là công cụ Lego/màu legacy độc lập, không tham gia pipeline camera USB YOLO.


## 10. Decision Engine stabilization v0.6.2-dev.5

- Hysteresis rời vùng có hai lớp: detector chỉ xác nhận rời sau khi footpoint vượt biên ngoài (footpoint nằm trong dải đệm không gian quanh đa giác (`KHOAI_ZONE_EXIT_BUFFER_RATIO`, mặc định 2% cạnh ngắn của frame)) và duy trì ngoài đủ `KHOAI_EXIT_CONFIRM_SECONDS`; Decision Engine tiếp tục giữ phiên thêm `KHOAI_DECISION_EXIT_HYSTERESIS_SECONDS`. Trong thời gian chờ, bộ đếm ân hạn tiếp tục chạy và trạng thái ALARM không bị hạ chỉ bởi một frame ngoài vùng.
- `session_id` được tạo cho phiên xâm nhập, tồn tại qua handover Track hợp lệ và được backend dùng để gộp Incident. Cooldown vẫn là lớp phụ, không thay thế session identity.
- Handover yêu cầu Track mới `inside=True`; `KHOAI_HANDOVER_MATCH_RADIUS` và `KHOAI_HANDOVER_EXCLUSION_RADIUS` cấu hình độc lập.
- Mỗi sự kiện dành trước `evidence_filename`; khi ảnh được ghi, metadata chuyển sang `evidence_status=available`. Khi ảnh hết hạn, tên file được giữ, `evidence_url` bị xóa và trạng thái chuyển `expired`. Bản ghi cũ không có filename được giao diện ghi rõ là dữ liệu Evidence cũ không xác định.
- Giới hạn Track: nếu mất quan sát lâu hơn cửa sổ handover 4,25 giây, ID mới không kế thừa phiên/bộ đếm. Characterization tests tại 5/6/8/10 giây mô tả giới hạn hiện tại, không phải tiêu chí yêu cầu kế thừa.
- `SUSPICIOUS` được kích hoạt khi Track tích lũy 30 giây ở vùng cảnh báo với gián đoạn tối đa 4 giây, hoặc có ít nhất 3 lần tiến sát (mỗi lần liên tục tối thiểu 2 giây) trong cửa sổ 120 giây. Nhánh đếm số lần tiến sát chỉ đáng tin khi Track ID được duy trì: một lần mới đòi hỏi rời vùng đệm hơn 4 giây, trong khi handover chỉ ghép khoảng trống tối đa 3,5 giây; vì vậy các lần tiến sát tách bởi đổi ID không được cộng dồn đáng tin cậy. Nhánh tích lũy 30 giây không phụ thuộc điều kiện giữ nguyên ID nếu handover hợp lệ. Các ngưỡng cấu hình bằng `KHOAI_SUSPICIOUS_SECONDS`, `KHOAI_SUSPICIOUS_GAP_SECONDS`, `KHOAI_SUSPICIOUS_APPROACH_MIN_SECONDS`, `KHOAI_SUSPICIOUS_APPROACH_COUNT` và `KHOAI_SUSPICIOUS_APPROACH_WINDOW_SECONDS`. Đây là heuristic hiện diện, không phải nhận diện hành vi phạm pháp; trạng thái này nâng mức tổng hợp lên WARNING, không tự kích hoạt ALARM.

### Release hygiene and test diagnostics

- `pytest.ini` bật `faulthandler_timeout=30` để in stack trace nếu test bị treo. Chạy toàn bộ suite bằng `python -m pytest -q` trong môi trường có đủ dependencies.
- Incident vẫn được gộp theo từng `session_id`; chưa triển khai một Incident OPEN chung cho nhiều người/phiên cùng đợt báo động. Dashboard có thao tác ACK tất cả các incident đang mở.
- Trước khi phát hành, chạy `python tools/validate_release_archive.py <archive.zip>`. Quy trình chặn ZIP chứa SQLite runtime, ảnh Evidence, file `.env` thật, cache hoặc chuỗi credential nghi vấn.
- ZIP phát hành không chứa `data/*.sqlite3` hoặc `ai/zone.json`; bản cài đặt tạo DB khi khởi động và dùng `ai/zone.json.example` làm mẫu.

### Chưa xác minh

- Các ngưỡng 8% (bán kính ghép), 8% (bán kính loại trừ), hệ số nới vùng 1,04, thời gian xác nhận rời và ân hạn 8 giây chưa được hiệu chỉnh trên camera USB thật.
- Handover vẫn là heuristic vị trí, không nhận dạng danh tính. Mất Track quá 4,25 giây có thể reset phiên/bộ đếm.
- Chưa kiểm chứng YOLO inference thực tế, camera USB, ESP32/RFID/servo/buzzer hoặc còi vật lý.

## Tài khoản quản trị riêng (bổ sung)

Có thể khởi tạo tài khoản quản trị cá nhân thay cho việc dùng chung `KHOAI_ADMIN_TOKEN`:

1. Trong `.env`, đặt `KHOAI_BOOTSTRAP_ADMIN_USERNAME`, `KHOAI_BOOTSTRAP_ADMIN_PASSWORD` (tối thiểu 12 ký tự) và tùy chọn `KHOAI_BOOTSTRAP_ADMIN_NAME`.
2. Khởi động backend. Tài khoản bootstrap chỉ được tạo khi bảng `admin_users` chưa có tài khoản nào; mật khẩu được băm PBKDF2-HMAC-SHA256.
3. Đăng nhập trên giao diện bằng username/password. Phiên được lưu trong cookie HttpOnly, SameSite=Strict.
4. Sau khi đăng nhập, có thể tạo tài khoản khác qua `POST /api/admin/users` (admin session). Vai trò `viewer` chỉ được xem dữ liệu vận hành; không được xem nhật ký hệ thống/danh sách tài khoản hoặc gọi API thay đổi dữ liệu.
5. Sau khi xác nhận tài khoản cá nhân hoạt động, xóa mật khẩu bootstrap khỏi `.env`. `KHOAI_ADMIN_TOKEN` vẫn được giữ làm cơ chế tương thích/khôi phục cũ; không chia sẻ token này giữa người vận hành.

Các API bổ sung:
- `POST /api/auth/login`, `GET /api/auth/me`
- `GET/POST /api/admin/users`
- `GET /api/incidents/{incident_id}/timeline`
- `GET /api/ai/explainability`
- `GET /api/cameras/center`
- `GET /api/history/advanced?kind=system|access|security&q=...&start=YYYY-MM-DD&end=YYYY-MM-DD`

Lưu ý dữ liệu: AI Explainability chỉ trình bày nguyên nhân/đầu vào khi detector thực sự cung cấp; nếu thiếu dữ liệu, API trả lời UNKNOWN hoặc thông báo chưa có diễn giải, không tự dựng lý do. Camera Control Center không tự suy ra FPS/kết nối ESP32-CAM từ URL cấu hình; trường chưa có telemetry được đánh dấu chưa xác minh.

## Spatial Mapping / Homography (dev.20)

- Camera USB ngoài là nguồn ảnh hiệu chuẩn mặc định (`KHOAI_CAMERA_ID=usb_external`).
- `PUT /api/camera/spatial-mapping` nhận các cặp `image_points` (pixel) và `floor_points` (X,Y mặt sàn), `floor_units`, `max_rms_error`. API chỉ hiệu chuẩn khi camera đang online và dùng đúng `frame_size` đọc từ frame thực tế gần nhất.
- Tối thiểu 4 cặp điểm. Nên dùng nhiều điểm phân bố trên toàn mặt sàn; với đúng 4 điểm, Homography có thể khớp chính xác về mặt toán học nên RMS gần 0 không chứng minh calibration chính xác. Trường `validation_level` phản ánh giới hạn này.
- `GET /api/camera/spatial-mapping` trả trạng thái calibration và tọa độ sàn của Track đang hiện diện. `floor_xy` là `null` khi chưa hiệu chuẩn, camera ID không khớp, độ phân giải đổi hoặc calibration đã bị vô hiệu hóa.
- `DELETE /api/camera/spatial-mapping` vô hiệu hóa calibration. Phải gọi khi camera bị di chuyển/đổi góc; hệ thống không tự xác định được camera đã dịch chuyển vật lý chỉ từ việc độ phân giải còn nguyên.
- Tệp cấu hình mặc định: `ai/homography.json` (có thể đổi bằng `KHOAI_HOMOGRAPHY_FILE`). Tệp mẫu `ai/homography.example.json` luôn ở trạng thái disabled.
- Mapping chỉ là phép chiếu lên một mặt phẳng; không tạo tọa độ Z/3D. Tọa độ mapping không tham gia Decision Engine, vùng cấm, WARNING hay ALARM.
- Tọa độ kho phải cùng hệ đơn vị và được đo thực tế. Không dùng kích thước mô hình Three.js minh họa làm số đo hiệu chuẩn.


## KhoAI v0.6.2-dev.24.2

Bản này tiếp tục gia cố Telegram Integration: cursor gửi cảnh báo riêng từng private chat, retry có giới hạn, xử lý `retry_after`, log không chứa bot token, cắt HTML an toàn, che UID trong thông báo và chờ evidence xuất hiện. Username quản trị được áp dụng unique không phân biệt hoa/thường. Docker healthcheck chỉ kiểm tra tiến trình/API còn phản hồi; trạng thái camera/AI được theo dõi riêng qua `/api/health` để máy không có camera không bị Docker đánh dấu unhealthy chỉ vì camera đang ngắt.
