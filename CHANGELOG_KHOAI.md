## v0.6.2-dev.24.66.8 — Red-Team Robustness Fixes

- Decision Engine bỏ qua `authorized_zones` sai kiểu và dùng dwell mặc định an toàn với chuỗi, bool, NaN/Infinity hoặc số vượt miền.
- Chuẩn hóa UID hoa/thường và dấu phân cách ở các thao tác tạo vé, kiểm tra vé, gắn quyền và thu hồi; thu hồi xóa được vé chờ bất kể kiểu chữ.
- Giới hạn hàng đợi vé RFID chờ bằng `KHOAI_RFID_MAX_PENDING_TICKETS` (mặc định 1024, tối đa 10000), tự dọn vé hết hạn; khi đầy không tạo ticket mới và API báo rõ.
- Telegram `/ack` yêu cầu đúng một ID dương trong miền INTEGER SQLite; callback ACK cũng từ chối ID ngoài miền.
- Bộ che Telegram nhận dạng UID dạng cặp byte phân cách bằng dấu `:` hoặc khoảng trắng.
- Chưa chạy pytest sau các thay đổi này; xem `TEST_REPORT_v0.6.2-dev.24.66.8.txt`.

## v0.6.2-dev.24.66.7 — Deployment Hardening

- Thêm middleware header bảo mật: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, HSTS khi kết nối HTTPS; CSP ở chế độ report-only mặc định.
- Thay thông báo lỗi nội bộ ở các route camera, stream và spatial mapping bằng thông báo chung; chi tiết được ghi vào log. Lỗi validation nghiệp vụ vẫn giữ HTTP 4xx.
- Giới hạn peer WebRTC đồng thời theo process bằng `KHOAI_WEBRTC_MAX_PEERS` (mặc định 4, tối đa 32).
- Thêm debounce RFID theo cặp thiết bị/thẻ trong giao dịch SQLite; lần quẹt trùng không trừ quota, không tạo vé và không kích hoạt mở cửa lần nữa.
- Hỗ trợ registry API key riêng theo thiết bị qua `KHOAI_DEVICE_API_KEYS_JSON`; firmware gửi `X-Device-ID` và `X-API-Key`, từ chối key chưa cấu hình.
- Thêm tùy chọn HTTPS có xác minh CA cho firmware RFID; mặc định vẫn là HTTP để tương thích thiết bị đang triển khai. Tự host Three.js/Vizzu và bật CSP enforce chưa hoàn tất vì chưa có quyền mạng để lấy artifact chính thức.
- Đối chiếu firmware dev.9 với phần cứng hiện tại: giữ pin RC522/servo/còi/LED và timing servo; giữ cấu hình ESP32-CAM QVGA, tắt Wi-Fi sleep và fallback PSRAM/DRAM. Cập nhật hướng dẫn RFID cho endpoint, cổng, API key, Device ID và trường phản hồi hiện hành; không chép thông tin Wi-Fi cá nhân từ ZIP.
- Chưa chạy pytest, Docker build, kiểm thử ESP32/camera hay kiểm tra triển khai thực tế trong lượt này.

## v0.6.2-dev.24.66.6 — Telegram Upgrade & Privacy Hardening

- Hỗ trợ cursor Telegram 24.1 ở cả hai schema `telegram_state(key,value)` và `telegram_state(last_sent_id)`; schema không nhận diện được chỉ ghi cảnh báo rồi tiếp tục khởi động.
- Lệnh `/alerts` dùng chung bộ che thông tin Telegram, tải UID/tên thẻ và chi tiết sự kiện; bỏ `details_json` thô khỏi kết quả đã che.
- Thêm fallback che chuỗi UID hex 8–20 ký tự và UID ngắn có nhãn; giữ nguyên Track ID, số đếm, năm và cổng.
- Đánh dấu WARNING phát lại từ outbox cũ để gộp ngay thành tin tổng hợp; sự kiện SEVERE tiếp tục gửi riêng.
- Sửa test migration để dùng đúng schema 24.1 và thêm regression coverage cho privacy/fallback/digest.
- Chưa chạy pytest hoặc kiểm thử Telegram thật trong lượt này.

## v0.6.2-dev.24.66.5 — Hero Visual Alignment

- Đặt lõi radar theo tâm tuyệt đối của vòng tròn để giữ vị trí giữa ổn định qua các breakpoint.
- Gỡ chữ K AI trang trí khỏi tất cả tiêu đề mục và xóa quy tắc CSS chỉ dùng cho dấu này.
- Giữ nhãn “VỊ TRÍ KHO · HÀ NỘI” trong hình minh họa.
- Kiểm tra cấu trúc HTML/CSS; chưa render lại bằng Chromium.

## v0.6.2-dev.24.66.4 — Warehouse Location Label

- Thay hai con số tọa độ trong hero bằng nhãn tĩnh “VỊ TRÍ KHO · HÀ NỘI”; không biểu thị dữ liệu GPS trực tiếp.
- Chưa kiểm thử lại bố cục trên trình duyệt sau thay đổi nhãn.

## v0.6.2-dev.24.66.3 — Security & Shortcut Follow-up

- Sửa handler phím tắt để bỏ qua mọi phím không phải số trước khi tính chỉ số; chuyển sang Alt+Shift+số để không chặn Alt+← và giảm xung đột phím tắt trình duyệt.
- Bắt đầu giao dịch SQLite `BEGIN IMMEDIATE` trước khi đếm admin đang hoạt động và đổi tài khoản, ngăn hai yêu cầu đồng thời cùng hạ quyền admin cuối cùng.
- Rate limit đăng nhập tiếp tục tính theo IP; Docker chỉ tin proxy được khai báo qua `KHOAI_TRUSTED_PROXY_IPS` (mặc định loopback). Chưa thêm khóa theo username để tránh tạo cơ chế khóa tài khoản có thể bị lạm dụng từ xa.
- Chưa chạy pytest hoặc kiểm thử đồng thời/khai thác thật.

## v0.6.2-dev.24.66.2 — Reliability & Interaction Refinements

- Thêm trạng thái đang xác thực, spinner và phản hồi rung nhẹ khi đăng nhập sai; bổ sung phím tắt điều hướng cho các tab đang hiển thị.
- Giới hạn reconnect tự động camera ngoài ở 5 lần với exponential backoff; sau đó giữ fallback và cho phép người vận hành thử lại thủ công.
- Đánh dấu khung hình cũ khi vượt quá ngưỡng theo FPS (tối thiểu 5 giây), chuyển trạng thái an ninh thành chưa xác định và xóa marker Track cũ khỏi mô hình 3D.
- Tuần tự hóa và gộp dữ liệu cập nhật Vizzu để animation mới nhất không chạy chồng lên animation đang phát.
- Rà soát bảo mật: `/api/history/advanced` không xuất `session_id`; thay đổi role, trạng thái hoặc mật khẩu thu hồi session tài khoản; xác thực session khi DB lỗi trả 503. Không phát hiện fail-open ở các luồng xác thực đã rà soát. Middleware audit ghi log sau thao tác và lỗi ghi audit chỉ ảnh hưởng nhật ký, không được xem là cơ chế xác thực.
- Chưa kiểm thử Chromium, camera thật, WebRTC, WebSocket metadata dưới sự cố mạng hoặc kiểm thử xâm nhập.

## v0.6.2-dev.24.66.1 — Frontend Usability Refinements

- Đưa các thẻ số liệu lên trước khung giới thiệu; Việt hóa nhãn trạng thái và điều hướng; nâng các cỡ chữ nhỏ lên tối thiểu 12px và vùng thao tác chính lên 44px.
- Chia form thẻ thành hai cột trên màn rộng, thu gọn khoảng cách form đăng nhập và làm rõ nút đăng nhập chính.
- Khôi phục nút đóng đăng nhập bằng chế độ xem chỉ đọc; khóa thao tác ghi và không gọi lại hộp thoại đăng nhập liên tục khi API trả 401.
- Giữ số liệu chờ trong lúc module biểu đồ tải; biểu đồ thanh nội bộ vẫn hiển thị khi Vizzu không khả dụng.
- Sửa trạng thái tab để phần Quản trị chỉ hiện khi được chọn; tăng độ tương phản nhãn sự kiện camera.
- Không tự host Three.js/Vizzu trong bản này; sơ đồ 2D và biểu đồ thanh vẫn là phương án dự phòng.

## Verification dev.24.66.1

- `node --check` cho các module frontend đã sửa: đạt.
- Phân tích HTML và kiểm tra cân bằng ngoặc CSS: đạt.
- Chưa kiểm thử lại Chromium, backend thật, đăng nhập/session, camera thật hoặc WebGL.

---

## v0.6.2-dev.24.64 — Backend Reliability & Documentation Cleanup

- Cập nhật phần mở đầu README, tiêu đề phiên bản và liên kết báo cáo để phản ánh đúng dev.24.64; giữ các ghi chú phiên bản cũ ở phần lịch sử.
- Chuẩn hóa khoảng trắng và mở rộng các câu lệnh `try/except`/điều kiện viết gọn trong bảy adapter Telegram: `api_client.py`, `polling.py`, `bot.py`, `notifier.py`, `notifier_delivery.py`, `notifier_digest.py` và `command_handlers.py`. Không thay đổi luồng xử lý.
- Tối ưu UID redaction: mỗi payload chỉ biên dịch một regex alternation theo thứ tự UID dài trước, thay vì chạy một regex cho mỗi UID trên từng trường văn bản; giữ nguyên ranh giới token và so khớp không phân biệt hoa/thường.
- Session validation cache chuyển sang LRU có khóa đồng bộ, TTL 2 giây và giới hạn cứng 2.048 phần tử; cache key phân biệt validator được inject. Lỗi DB vẫn không được cache.
- Telegram lease acquire/renew sử dụng đồng hồ SQLite ngay trong câu lệnh SQL, tránh timestamp Python cũ khi thao tác phải chờ khóa DB.
- Bổ sung kiểm thử hồi quy cho cache session, UID masking và quyền sở hữu/expiry của Telegram lease.
- Không thay đổi `pytest-asyncio` trong requirements theo xác nhận của người dùng. Không thay đổi API, schema, Decision Engine, YOLO/ByteTrack, ROI hoặc firmware.

## Verification dev.24.64

- pytest: 434 passed, 1 warning (Starlette TestClient cookie deprecation).
- JavaScript tests: 9 passed, 0 failed.
- compileall: passed.
- Regression tests dev.24.64: 3 passed.
- Not verified: Docker build, live Telegram API, physical cameras/ESP32, browser visual behavior.

---

## v0.6.2-dev.24.63 — Backend Dependency Cleanup

- `telegram/callbacks.py`: bổ sung import `Any`, chuẩn hóa định dạng và giữ nguyên luồng ACK, phản hồi callback, xử lý hủy tác vụ và dọn inline keyboard.
- `telegram/integration.py`: bỏ lazy import `backend.app.main`; `build_telegram_bot()` nhận service bundle tường minh từ composition root. Các persistence adapter tiếp tục chỉ phụ thuộc vào contract dịch vụ được truyền vào.
- `main.py`: thêm `telegram_backend_services()` để cung cấp DB session, business timezone/clock và app version cho Telegram; lifespan truyền bundle này vào factory.
- `auth.py`: session cache nhận validator qua tham số tùy chọn; `main.py` giữ monkeypatch point mà không ghi đè biến toàn cục trong module auth.
- `privacy.py`: UID redaction nhận `known_uids_provider` qua tham số; `main.py` giữ injection point mà không thay đổi global provider của module privacy.
- Loại bỏ source-marker comment giả lập khai báo route; cập nhật kiểm thử để xác minh route trên FastAPI runtime registry.
- Không thay đổi endpoint, HTTP method, session policy, cache TTL, UID masking policy, Telegram payload, DB schema hoặc firmware.

## Verification dev.24.63

- pytest: 431 passed, 1 warning.
- JavaScript tests: 9 passed, 0 failed.
- compileall: passed.
- Callback type-hint resolution: passed.
- FastAPI endpoint registry: 55 endpoint signatures, no duplicate signatures.
- Telegram integration source: no import of `main.py`.
- Release archive validation and ZIP integrity: pending final packaging.
- Not verified: Docker build, live Telegram delivery, physical cameras, browser visual behavior.

---

## v0.6.2-dev.24.62 — Admin Authentication Rate-Limit Split

- Tách cơ chế làm sạch failure window và kiểm tra giới hạn xác thực header quản trị sang `backend/app/auth_rate_limit.py`.
- `auth.py` giữ `_record_auth_failure()` và `_check_admin_header()` làm compatibility wrappers, đồng thời truyền lock, failure map, ngưỡng cấu hình và credential matcher qua tham số.
- Giữ nguyên giới hạn cấu hình, cửa sổ thời gian, thông báo lỗi, HTTP 429, cách xóa bộ đếm khi xác thực thành công và các điểm injection/monkeypatch hiện có.
- Không thay đổi session, role, API, schema DB hoặc xác thực thiết bị.

## Verification dev.24.62

- pytest: 431 passed, 1 warning.
- JavaScript tests: 9 passed, 0 failed.
- compileall: passed.
- Release archive validation and ZIP integrity: passed.
- Not verified: Docker build, live Telegram delivery, physical cameras, browser visual behavior.

---

## v0.6.2-dev.24.59 — Telegram Command Responsibilities Split

- Tách xử lý lệnh và kiểm tra allowlist sang `telegram/command_handlers.py`.
- Tách xử lý callback ACK sang `telegram/callbacks.py`.
- Tách vòng lặp polling, rate-limit và auth recovery probe sang `telegram/polling.py`.
- Giữ `telegram/commands.py` làm compatibility facade với `TelegramCommandMixin`; `TelegramBot` và các import hiện tại tiếp tục sử dụng được.
- Không thay đổi cú pháp lệnh, allowlist, callback ACK, polling offset, timeout hoặc cơ chế auth recovery.

## Verification dev.24.59

- pytest: 427 passed, 1 warning.
- JavaScript tests: 9 passed, 0 failed.
- compileall: passed.
- Release archive validation: pending packaging.
- Not verified: Docker build, live Telegram delivery, physical cameras, browser visual behavior.

---

## v0.6.2-dev.24.58 — Telegram Notifier Responsibility Split

- Tách `_event_text()` và `_process_outbox_item()` sang `telegram/notifier_delivery.py`, chịu trách nhiệm định dạng sự kiện và gửi text/photo theo trạng thái outbox.
- Tách `_summarize_delayed_warnings()` sang `telegram/notifier_digest.py`, chịu trách nhiệm gom các WARNING bị trì hoãn thành digest.
- Giữ `telegram/notifier.py` làm coordinator xử lý hàng đợi từng chat và vòng lặp notifier.
- Giữ nguyên các method mixin, context/config/API được inject; không thay đổi schema DB, API backend hoặc giao thức Telegram dự kiến.

## Verification dev.24.58

- pytest: 427 passed, 1 warning.
- JavaScript tests: 9 passed, 0 failed.
- compileall: passed.
- Release archive validation: completed by packaging tool.
- Not verified: Docker build, live Telegram delivery, physical cameras, browser visual behavior.

---

## v0.6.2-dev.24.56 — Telegram Persistence Adapter Split

- Tách khởi tạo schema và migration Telegram sang `telegram/persistence_schema.py`.
- Tách callback truy vấn trạng thái, cảnh báo, ảnh bằng chứng và outbox sang `telegram/persistence_queries.py`.
- Tách callback ghi nhận xác nhận cảnh báo, cập nhật outbox, lease và runtime state sang `telegram/persistence_delivery.py`.
- `telegram/integration.py` chỉ còn nhiệm vụ composition, giữ nguyên `build_telegram_bot()` và `TelegramContext`.
- Giữ import `backend.app.telegram.integration.build_telegram_bot` và cơ chế import backend lazy.

# v0.6.2-dev.24.54 — Authentication Primitive Split

- Tách các primitive xác thực khỏi `auth.py` thành ba module theo trách nhiệm:
  - `security_credentials.py`: so sánh credential, PBKDF2 password hash/verify và chính sách kiểm tra admin secret.
  - `session_tokens.py`: tạo SHA-256 digest cho session token; không lưu cookie thô.
  - `uid_normalization.py`: chuẩn hóa và xác thực RFID UID.
- Giữ `auth.py` làm compatibility facade, tiếp tục export các symbol cũ để các router, main composition root và test/integration không phải đổi điểm import.
- Không thay đổi thuật toán PBKDF2, số vòng lặp, định dạng hash, SHA-256 session digest, UID regex, API, schema DB hoặc hành vi xác thực.

## Verification dev.24.54

- pytest: pending final run.
- JavaScript tests: pending final run.
- compileall: pending final run.
- Release ZIP validator and archive integrity: pending final run.
- Not verified: Docker build, live Telegram, physical cameras, browser visual behavior.

---

# v0.6.2-dev.24.53 — Telegram Adapter Responsibility Split

- Tách xử lý Telegram thành bốn module theo trách nhiệm:
  - `telegram/formatting.py`: Telegram API error đã làm sạch, HTML truncation và escape nội dung.
  - `telegram/api_client.py`: HTTP API operations và gửi text/photo.
  - `telegram/commands.py`: allowlist, command/callback handling, polling và auth probe.
  - `telegram/notifier.py`: xử lý outbox theo từng chat, retry text/photo và gom WARNING trì hoãn.
- Giữ `telegram/bot.py` làm facade tương thích và supervisor: tiếp tục export `TelegramBot`, `TelegramConfig`, `TelegramContext`, `TelegramAPIError`, `load_config`, `telegram_enabled`, `_truncate_html` và `_lease_heartbeat_loop`.
- `TelegramBot` ghép các mixin nội bộ; giữ nguyên API công khai, callback context, lease lifecycle, auth circuit breaker, retry policy và per-chat isolation.
- Không thay đổi schema DB, Telegram endpoint/payload, quyền allowlist, AI, YOLO/ByteTrack, Decision Engine, frontend hoặc firmware.

## Verification dev.24.53

- `python -m pytest -q`: 419 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release ZIP validator and archive integrity: passed.
- Not verified: Docker build, live Telegram delivery, physical cameras, browser visual behavior.

---

# v0.6.2-dev.24.52 — Camera Stream Route Split

- Tách `routes/camera_streams.py` thành bốn router theo ranh giới giao thức và thiết bị:
  - `routes/camera_usb_stream.py`: MJPEG từ camera USB và detector.
  - `routes/camera_webrtc.py`: WebRTC offer, peer lifecycle và cleanup.
  - `routes/camera_stream_metadata.py`: WebSocket metadata, xác thực session và kiểm tra Origin.
  - `routes/inside_camera_stream.py`: proxy MJPEG từ ESP32-CAM.
- Giữ `routes/camera_streams.py` làm compatibility facade; giữ nguyên factory, handler names và điểm đăng ký tại `main.py`.
- Giữ nguyên URL, HTTP method, auth dependencies, session validation, stream-manager accounting, timeout và cleanup.
- Không thay đổi AI, YOLO/ByteTrack, Decision Engine, database schema, frontend hoặc firmware.

## Verification dev.24.52

- `python -m pytest -q`: 419 passed, 1 warning.
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release ZIP validator: passed; ZIP integrity check passed.

---

# v0.6.2-dev.24.51 — Authentication Route Split

- Tách đăng nhập, đọc phiên hiện tại và đăng xuất sang `routes/auth_sessions.py`.
- Tách CRUD tài khoản quản trị sang `routes/admin_users.py`.
- Giữ `routes/auth.py` làm compatibility facade; `create_auth_router()` tiếp tục ghép hai router con và giữ nguyên điểm đăng ký tại composition root.
- Giữ nguyên URL, HTTP method, kiểm tra rate-limit, xác thực mật khẩu, nâng cấp hash, cookie session, thu hồi session, quy tắc không tự hạ quyền và bảo vệ admin cuối cùng.
- Không thay đổi schema DB, API payload, frontend, AI, tracking, Decision Engine hoặc firmware.

## Verification dev.24.51

- Sẽ ghi kết quả sau khi chạy kiểm thử đầy đủ và release validator.

---

# v0.6.2-dev.24.47 — Incident and Alert Read-Model Split

- Tách truy vấn Incident và timeline sang `services/incident_read_service.py`.
- Tách lọc, ánh xạ và che UID của security alert sang `services/security_alert_query_service.py`.
- Giữ `IncidentQueryService` làm compatibility facade để bảo toàn giao diện mà router và các kiểm thử hiện tại đang sử dụng.
- Đồng bộ dependency DB và UID masker qua facade; không thay đổi endpoint, phân quyền, SQL filter, response fields hoặc hành vi che UID.
- Bổ sung kiểm thử trực tiếp cho hai service mới.
- Không thay đổi Decision Engine, YOLO/ByteTrack, camera, database schema hoặc firmware.

## Verification dev.24.47

- Sẽ được điền sau khi chạy kiểm thử và release validator.

---

# v0.6.2-dev.24.44 — Incident Event Store Extraction

- Tách persistence Incident Event và liên kết security event khỏi `IncidentStore` sang `services/incident_event_store.py`.
- Giữ `IncidentStore.record_event()` và `IncidentStore.link_event()` làm compatibility delegates để không đổi các điểm gọi hiện có.
- Giữ nguyên cooldown theo event type/track, xử lý timestamp lỗi, INSERT OR IGNORE, cập nhật event_count và bảo toàn details khi liên kết Incident.
- Bổ sung kiểm thử độc lập cho ghi event, cooldown, liên kết và trường hợp source không tồn tại.
- Không thay đổi API, schema database, Decision Engine, camera hoặc firmware.

## Verification dev.24.44

- Kết quả kiểm thử được ghi sau khi chạy đầy đủ suite và release validator.

---

# v0.6.2-dev.24.39 — Device Read Service Extraction

- Extracted legacy scan-history and last-unknown-card read logic from `routes/devices.py` into `services/device_read_service.py`.
- Preserved route paths, authentication dependencies, response fields, denial-reason lookup, and role-based UID masking.
- Kept device heartbeat endpoint unchanged.

## Verification dev.24.39

- `python -m pytest -q`: 401 passed, 1 warning.
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.

# v0.6.2-dev.24.38 — External Event Processor Extraction

- Tách xử lý nghiệp vụ sự kiện camera ngoài khỏi `routes/external_events.py` sang `services/external_event_processor.py`.
- Service nhận payload, dependency runtime và callback lưu cảnh báo qua tham số; không đăng ký route và không import `main.py`.
- Router giữ xác thực admin, endpoint `/api/events` và fallback tương thích cho `persist_external_alert`.
- Giữ nguyên các nhánh outside/inside, đối chiếu lượt quẹt, sai vùng, lưu trú, số thùng, generic event và response API.
- Bổ sung kiểm thử cho cập nhật trạng thái camera ngoài, heuristic tailgating và ghi generic event.

## Verification dev.24.38

- Kết quả kiểm thử được ghi sau khi chạy toàn bộ suite và release validator.
- Camera vật lý, Docker, browser visual và Telegram live không được xác minh trong lượt này.

---

# v0.6.2-dev.24.29 — Incident Reconciliation Service Extraction

- Tách quy trình đối soát Incident định kỳ khỏi `CameraEventSyncService` sang `backend/app/services/incident_reconciliation.py`.
- Service chỉ đóng Incident khi detector xác nhận `SAFE`, detector tồn tại và `anti_theft_enabled` đang bật.
- Lỗi import/truy cập detector hoặc lỗi khi đọc trạng thái detector đều fail-closed: không mở DB để đóng Incident.
- `main.py` giữ `_reconcile_open_incidents()` làm compatibility entry point và truyền lại các dependency hiện hành trước mỗi lần chạy để bảo toàn điểm monkeypatch.
- `CameraEventSyncService` chỉ còn nhiệm vụ lưu và phân loại sự kiện camera; không còn sở hữu logic reconciliation.
- Không thay đổi Decision Engine, quy tắc YOLO/ByteTrack, API hay cấu trúc DB.

## Verification dev.24.29

- Kết quả kiểm thử, compile và đóng gói được ghi trong `TEST_REPORT_v0.6.2-dev.24.29.txt` sau khi chạy.
- Camera vật lý, Docker, trình duyệt và tích hợp Telegram live không được xác minh trong lượt này.

---

# v0.6.2-dev.24.22 — Incident Store Service Extraction

- Tách các thao tác lưu trữ/vòng đời Incident độc lập khỏi `main.py` sang `backend/app/services/incident_store.py`.
- Module mới quản lý mở/reopen Incident, ghi Incident Event có cooldown/idempotency, liên kết security event với Incident, đóng intrusion đã được ACK khi trạng thái SAFE, đóng health incident và phân loại camera outage/AI health.
- Service nhận business clock, cooldown, thời hạn còi và detector-state provider qua constructor; không import `main.py`, không đăng ký HTTP route.
- `main.py` giữ compatibility wrappers để không đổi các điểm gọi hiện có và duy trì monkeypatch behavior của kiểm thử.
- Không chuyển `_sync_usb_camera_events`, `_incident_status`, `_reconcile_open_incidents` hoặc worker trong đợt này; các phần đó vẫn phụ thuộc nhiều vào DB, detector và ứng dụng.

## Verification dev.24.22

- `python -m pytest -q`: 368 passed, 1 warning.
- JavaScript tests, compileall và release validator: sẽ ghi kết quả sau khi chạy đóng gói.
- Camera vật lý, Docker, trình duyệt, Telegram live và ESP32 không được xác minh trong lượt này.

---

# v0.6.2-dev.24.9 — Authentication Route Extraction

- Tách các endpoint đăng nhập, thông tin session, quản lý tài khoản admin và logout sang `backend/app/routes/auth.py`.
- Router nhận các service qua `AuthRouteServices` Protocol; không import ngược `main.py`, tránh circular import.
- `main.py` giữ vai trò composition root và truyền DB/auth/session dependencies vào router.
- Giữ nguyên endpoint, schema, cookie, phân quyền, audit log và quy tắc không tự khóa admin cuối cùng.
- Giảm `main.py` từ 1.746 xuống 1.643 dòng. Các nhóm camera, incident, RFID/access và history vẫn đang ở `main.py`.
- Thêm `ARCHITECTURE_BACKEND.md` ghi rõ trách nhiệm module, nguyên tắc tách tiếp và phần chưa tách.

## Verification dev.24.9

- `PYTHONPATH=. pytest -q`: 368 passed, 1 warning.
- `python -m compileall -q backend ai`: passed.
- Node tests và release validator: thực hiện khi đóng gói.
- Chưa xác minh Docker, Pylance/Pyright, browser, camera USB, Telegram API hoặc phần cứng thật.

# v0.6.2-dev.24.7 — Backend Foundation Split & UI Typography Cleanup

- Tách cấu hình runtime/path ra `backend/app/settings.py`; giữ nguyên tên biến được import trong `main.py` để tương thích các module hiện có.
- Tách vòng đời kết nối SQLite ra `backend/app/database.py`; `main.py` tiếp tục cung cấp wrapper `connect_db()` và `db_session()` để không thay đổi các điểm gọi hiện tại.
- Tách Pydantic request schemas ra `backend/app/schemas.py`; bổ sung kiểu đầu vào/đầu ra cho các validator đã có.
- Tách retention worker và dọn evidence/log/incident ra `backend/app/retention.py` dưới dạng `RetentionService`; các hàm cũ trong `main.py` được giữ làm wrapper tương thích.
- Giảm `backend/app/main.py` từ 2.470 xuống 2.267 dòng. Đây là đợt tách nền tảng đầu tiên, chưa phải hoàn tất phân rã toàn bộ router/service.
- Thay font Space Grotesk chưa được nạp bằng system font stack ổn định; chuẩn hóa các cỡ chữ 7–9px lên mức đọc được, tăng các nút điều hướng/chính lên chiều cao tối thiểu 44px.
- Thay icon điều hướng Unicode bằng SVG inline; điều chỉnh một số nhãn giao diện sang tiếng Việt. Không thay API, Decision Engine, camera, RFID, Telegram hoặc logic Digital Twin.
- Cập nhật kiểm thử giao diện để kiểm tra font stack, cỡ chữ tối thiểu và SVG navigation.

## Verification dev.24.7

- `python -m pytest -q`: 368 passed, 1 warning.
- `python -m compileall -q backend ai`: passed.
- `node --check` cho toàn bộ `.js` và `.mjs`: passed.
- `node --test tests/*.js tests/*.mjs`: 9/9 passed.
- Release archive validator: chạy khi đóng gói.
- Chưa chạy Docker build, Pylance/Pyright, browser visual regression hoặc camera/Telegram/ESP32 thật trong lượt này.

# KhoAI Changelog

## v0.6.2-dev.24.6 – Session Validation & Lease Safety

- Session validation now distinguishes invalid/expired sessions from temporary SQLite failures. Temporary failures are not cached as invalid; WebSocket closes with 1013, while invalid sessions close with 4401.
- Viewer UID redaction now includes registered card UIDs from a five-second cache, allowing message-only UID occurrences to be masked without generic hexadecimal matching. Structured UID fields remain redacted.
- Telegram lease heartbeat tracks the last confirmed renewal deadline, bounds retries by remaining TTL, and raises before lease expiry so the supervisor stops polling when ownership cannot be confirmed.
- Added regression coverage for message-only registered UIDs, ordinary hex-like text preservation, transient session-store errors, and lease expiry under prolonged renewal failure.
- Automated test results are environment-dependent; no real Telegram, Docker, Python 3.12, or multi-process staging test is claimed by this changelog.

# v0.6.2-dev.24 – Telegram Integration

- Tích hợp Telegram Bot tùy chọn trên backend dev.23.
- Whitelist private chat, status/alerts/ACK/snapshot, cảnh báo đẩy có evidence.
- ACK từ Telegram được ghi vào system_access_logs.
- Telegram mặc định tắt; lỗi Telegram không chặn backend/AI.
- Không mang theo frontend/backend/AI cũ, database, .venv, token hoặc tính năng gọi điện bên thứ ba.

# v0.6.2-dev.23.3.3 — Admin Authorization & Session Hardening

- Split authorization into `require_session` for operational read access and `require_admin_role` for administrator-only APIs and all protected writes.
- Resolve account role and active status from `admin_users` on every authenticated request; do not trust the role snapshot stored in `admin_sessions`.
- Viewer can read operational status, alerts, incidents, camera events/evidence, scans, and security/access history. Viewer cannot read system access logs, advanced system history, or administrator accounts.
- Remove authorization decisions from middleware. Middleware now records audit events only; endpoint dependencies enforce access and fail closed with HTTP 503 when session/role lookup fails.
- Store SHA-256 digests of session cookies in `admin_sessions`; audit records store only a shortened digest and history APIs never return a session identifier.
- Add one-time migration `2026-11-11_session_digest_v1`: invalidate all legacy sessions and clear legacy session identifiers from `system_access_logs`.
- Revoke a user's sessions whenever role, password, or active status changes. Add password update support to the administrator account endpoint.
- Update frontend role handling so viewers do not request administrator-only card/account data or render the system audit panel; operational dashboard refresh remains available.
- Add regression coverage for viewer restrictions, session hashing, system-log field filtering, role/password revocation, migration cleanup, and database-error fail-closed behavior.

## Verification

- Python pytest: 336 passed, 1 warning.
- The 58 focused authorization/session tests passed before the full-suite run.
- Python compilation and JavaScript syntax checks are recorded in `TEST_REPORT_v0.6.2-dev.23.3.3.txt`.
- No physical camera, ESP32, RC522, servo, or buzzer hardware was tested.

---

# v0.6.2-dev.23.3.2 — Camera Event Classification & Health Debounce

- Classify `camera_unstable` as `camera_outage` in both health-start and `health_fault` incident paths.
- Add Vietnamese labels for `camera_unstable` to camera event constants and advanced history.
- Add configurable `KHOAI_CAMERA_UNSTABLE_DELAY_SECONDS` (default 3.5s; bounded below the health escalation threshold when that threshold is non-zero).
- Debounce camera cadence WARNING and `camera_unstable` event together. A short hiccup that recovers before the delay creates no event, incident, WARNING, or recovery event.
- Keep health escalation anchored to the first crossing of the 0.5s frame-gap limit; the debounce does not restart the 30-second escalation clock.
- Preserve immediate fail-closed RFID gating from the stable-camera predicate; a newly observed bad frame gap clears pending tickets and active Track authorizations before auto-binding.
- Prevent an intermediate `camera_unstable` event once the camera has transitioned to `camera_offline`; recovery is represented by `camera_recovered`.
- Log sustained low cadence with measured capture FPS and maximum observed frame gap. Document approximately 3 FPS or higher; keep the 0.5s frame-gap threshold unchanged.
- Add regression tests for incident classification/grouping, short hiccups, sustained 1 FPS, 30-second escalation, long-stall recovery, RFID blocking, and frontend labels.

## Preserved security parameters

- RFID authorization TTL: maximum 60 seconds.
- Track authorization-loss timeout: 0.75 seconds.
- Decision Engine grace: 8 seconds.
- Health escalation: 30 seconds by default.
- Camera stable predicate: maximum frame gap 0.5 seconds; stable window and minimum frame count unchanged.

## Verification

- Python pytest: 330 passed, 1 warning.
- Node tests: 9 passed.
- Python compileall and targeted JavaScript syntax checks passed.
- Physical camera and ESP32/RFID hardware were not tested in this environment.

---

# v0.6.2-dev.24.1 – Security & Deployment Hardening

- Docker image now copies `config/profiles/` and initializes the runtime zone file from `ai/zone.json.example`; healthcheck fails when AI or camera is unavailable instead of accepting a degraded API-only container.
- Uvicorn enables proxy headers with an explicit trusted-proxy allowlist variable; configure `KHOAI_TRUSTED_PROXY_IPS` to the actual proxy addresses in deployment.
- Device API key must be a private secret of at least 32 characters and cannot be a known example value; failed device-key attempts are rate-limited per client IP per process.
- Viewer-facing access, scan, alert, incident, camera-event and history payloads mask RFID UIDs; admin retains full UID visibility.
- Prevent self-demotion/self-deactivation and prevent demotion/deactivation of the last active administrator.
- New PBKDF2-HMAC-SHA256 password hashes use 600,000 iterations; older supported hashes are upgraded after successful login; nonexistent usernames perform a dummy verification.
- Enforce minimum bootstrap-admin password length of 12 characters and case-insensitive username lookup.
- Revalidate session digests during active MJPEG streams and revalidate WebSocket sessions periodically; reject cross-origin WebSocket requests when Origin is supplied.
- Add finite ESP32-CAM upstream HTTP timeouts and prevent viewer GET requests from starting the AI detector as a side effect.
- RFID camera-ticket failure no longer returns a fabricated pending ticket; the API reports camera permission as unavailable.
- Replace BaseHTTPMiddleware audit hook with pure ASGI middleware and move SQLite audit writes to a worker thread; audit header-authenticated admin mutations as well.
- Add regression tests for Docker source layout, device-key placeholder rejection, viewer UID masking and administrator lockout prevention.

## Verification

- Python pytest: 344 passed, 1 DeprecationWarning.
- Python compileall: passed.
- Node syntax checks for frontend JavaScript: passed.
- Node tests: 9 passed.
- Release archive validator: run during packaging.
- Docker CLI was not available in the execution environment; an actual `docker build` and container `/api/health` smoke test were not run.
- Real camera, Telegram API, ESP32-CAM, ESP32/RC522 and physical hardware were not tested.

## Known remaining items

- Device API-key rate limiting is process-local; use one API worker or a shared limiter for multi-worker deployment.
- Reverse-proxy IP forwarding must be restricted to trusted proxy addresses via `KHOAI_TRUSTED_PROXY_IPS`; do not trust arbitrary forwarded headers.
- UID-only RFID remains cloneable; software masking protects viewer disclosure but does not strengthen the card's cryptographic authentication.
- ESP32 firmware still uses its existing transport and response model; HTTPS/pinned certificate and signed device responses require a separate firmware/security project.
- `BaseHTTPMiddleware` audit implementation has been replaced; additional ASGI middleware behavior should still be checked under the actual production proxy/server stack.

## v0.6.2-dev.24.2 — Telegram Reliability & Identity Hardening

- Tách delivery cursor theo từng private chat; lỗi một chat không chặn chat khác.
- Retry gửi cảnh báo có giới hạn; đọc `retry_after`; bỏ qua poison event sau số lần thử tối đa.
- Không ghi URL/token Telegram vào log; lỗi API chỉ ghi method/status.
- Cắt HTML theo nội dung hiển thị, giữ entity và thẻ hợp lệ; thay `disable_web_page_preview` bằng `link_preview_options`.
- Chỉ nhận allowlist ID dương; sửa `load_config({})`; ACK chỉ nhận chữ số ASCII; phản hồi callback và gỡ nút sau ACK.
- Chờ evidence xuất hiện trong thời gian ngắn trước khi gửi; che UID trong nội dung thông báo.
- Username admin unique không phân biệt hoa/thường; database cũ có username trùng sẽ dừng với thông báo rõ ràng, không tự đổi tài khoản.
- Docker healthcheck kiểm tra API còn phản hồi; camera/AI health tiếp tục hiển thị riêng, không biến mất camera thành trạng thái container unhealthy.

Chưa xử lý trong bản này: CSP/security headers, giới hạn WebRTC peer, tối ưu truy vấn evidence, chuẩn hóa lỗi API trả client, debounce RFID vật lý, HTTPS/chữ ký phản hồi firmware, phân quyền Telegram viewer/admin chi tiết và kiểm thử Telegram API thật.

## v0.6.2-dev.24.3 — Telegram Durable Outbox

- Thay delivery cursor kiểu “đã xử lý” bằng SQLite outbox duy nhất theo `(chat_id,event_id)`; cursor chỉ phục vụ discovery. Migration dev.24.2 replay các cảnh báo trong cửa sổ cấu hình, không coi cursor cũ là bằng chứng đã gửi. Hỗ trợ khởi tạo cursor mới và đọc watermark `telegram_state.last_sent_id` của nhánh dev.24.1 nếu có.
- Gửi text ngay, gắn ACK trên text, lưu `text_message_id`; ảnh là nhánh độc lập gửi reply theo `event_id` sau khi evidence chuyển `available`. Trạng thái ảnh `not_applicable/pending/sent/failed/expired`; TTL cấu hình.
- Retry mạng/timeout/5xx không giới hạn với backoff tối đa 15 phút; tôn trọng 429 `retry_after`; 403 chờ dài theo chat; 401/404 mở circuit breaker và probe `getMe` định kỳ. HTTP 400 parse entities có fallback plain text.
- Bổ sung sanitized API description, per-chat rate limit, lease SQLite chống chạy bot/polling đồng thời, admin API xem tình trạng và retry lỗi permanent; `/api/health` không chứa thông tin vận hành Telegram.
- Mask UID có cấu trúc và UID trong message mà không áp regex hex lên toàn bộ câu tiếng Việt; mặc định ẩn tên theo dữ liệu thẻ. Cảnh báo WARNING tồn đọng số lượng lớn được tổng hợp sau thời gian cấu hình; SEVERE luôn gửi riêng.
- Retention giữ nguyên security event còn outbox đang retry; dọn outbox terminal cùng vòng đời event. Các chat được xử lý độc lập song song; vẫn áp rate limit riêng từng chat.
- Delivery bảo đảm at-least-once, không phải exactly-once: tiến trình có thể dừng sau khi Telegram nhận tin nhưng trước khi ghi message ID vào SQLite, dẫn đến khả năng gửi trùng khi khôi phục.

### Verification dev.24.3

- `python -m pytest -q`: kiểm tra hồi quy toàn bộ; kết quả và cảnh báo ghi nhận trong biên bản build đi kèm.
- Chưa kiểm thử với Telegram token/bot thật, chưa xác minh hành vi mạng Telegram thực tế, và chưa kiểm tra nhiều tiến trình trên máy triển khai.

## v0.6.2-dev.24.4 — Telegram Recovery & Stream Privacy

- Telegram bot tiếp tục chờ lease với exponential backoff; heartbeat chịu lỗi SQLite tạm thời và vòng worker tự khởi động lại khi mất lease/lỗi tác vụ.
- Session validation của MJPEG USB và proxy ESP32-CAM chuyển sang `asyncio.to_thread`, cache tối đa 2 giây để không truy vấn SQLite trên mỗi frame/chunk.
- UID masking Telegram chỉ thay UID đã biết từ trường có cấu trúc/cards; bỏ regex hex đại trà làm hỏng thời lượng, Track ID, ngày tháng và từ tiếng Anh.
- Viewer API che UID trong cả `message` tự do khi UID có mặt trong dữ liệu có cấu trúc cùng sự kiện; thông báo auto-bind không còn ghi UID đầy đủ.
- `TELEGRAM_ENABLED` dùng parser fail-closed duy nhất; chuỗi rỗng và giá trị không hợp lệ được coi là tắt.
- Khi gộp WARNING tồn đọng, ảnh của từng sự kiện được đặt `not_applicable`, tránh gửi lại hàng loạt ảnh rời.
- Chưa xác nhận Telegram Bot API thật hoặc nhiều tiến trình trên máy triển khai.

## v0.6.2-dev.24.5 — Viewer UID Redaction & WebSocket Recovery

- Chuẩn hóa một hàm redaction payload dùng chung cho mọi API viewer: `/api/camera/events`, `/api/alerts`, `/api/history/advanced`, `/api/incidents`, timeline, logs và scans. Hàm thu thập UID từ trường có cấu trúc trong cùng payload rồi che đúng UID trong mọi chuỗi văn bản liên quan; không dùng regex hex tổng quát và không thay chuỗi con nằm trong từ thông thường.
- Giữ UID đầy đủ cho admin; viewer chỉ nhận UID đã che trong cả trường cấu trúc lẫn `message`/`explanation`/các trường văn bản lồng nhau.
- WebSocket `/ws/camera/streams` chuyển sang `_session_digest_valid_cached()` bất đồng bộ, dùng cùng cache 2 giây với stream MJPEG/proxy; lỗi xác minh phiên/DB đóng kết nối fail-closed bằng mã 1013, phiên hết hạn đóng 4401.
- Tách lease heartbeat thành `_lease_heartbeat_loop`; lỗi SQLite retry trong cùng chu kỳ sau 1–5 giây, không cộng thêm khoảng chờ 20 giây. Mất lease vẫn làm worker supervisor khởi động lại.
- Bổ sung regression tests cho UID ở alert/history/timeline, UID substring boundary, heartbeat SQLite lock và WebSocket validation lỗi 503 ở cả lúc kết nối lẫn khi đang chạy.

### Verification dev.24.5

- Kết quả kiểm thử được ghi trong `TEST_REPORT_v0.6.2-dev.24.5.txt`; không coi kết quả do mock là xác minh đa tiến trình hoặc Telegram API thật.
- Chưa thử Telegram Bot API thật, hai tiến trình tranh lease, phần cứng camera/ESP32/RC522, hoặc môi trường Docker production.

## v0.6.2-dev.24.8

- Tách các primitive xác thực, session và device-key sang `backend/app/auth.py`; giữ import tương thích tại `main.py`.
- Chuyển schema creation và migration SQLite sang `database.initialize_database`; `main.init_db()` chỉ còn là wrapper bootstrap.
- Loại bỏ decorator `@contextmanager` đặt nhầm trên `init_db()` trong bản trước; đảm bảo hàm khởi tạo DB được thực thi khi lifespan gọi.

## v0.6.2-dev.24.8 — Backend Refactor 2

- Tách authentication, session và device-key security primitives sang `backend/app/auth.py`.
- Tách schema creation và SQLite migrations sang `backend/app/database.py`.
- Tách UID redaction sang `backend/app/privacy.py`.
- Tách admin audit middleware sang `backend/app/audit.py`.
- Giữ các tên import tương thích trong `main.py` để hạn chế ảnh hưởng đến route, test và tích hợp hiện có.
- Sửa lỗi `init_db()` bị trang trí `@contextmanager` dù không phải generator context manager; trước đó gọi trực tiếp không thực thi phần thân hàm. Hàm khởi tạo DB hiện ủy quyền cho `initialize_database()`.

## v0.6.2-dev.24.10 — History Routes Extraction

- Tách `/api/history/advanced`, `/api/logs` và `/api/stats` sang `backend/app/routes/history.py`.
- Router nhận DB session, ngày nghiệp vụ, UID masking và session dependency qua `HistoryRouteServices`; không import ngược `main.py`.
- Giữ nguyên giới hạn truy vấn, bộ lọc lịch sử, quyền admin đối với system history và che UID đối với viewer.
- Cập nhật sơ đồ module backend và báo cáo kiểm thử.
- `main.py` giảm khoảng 75 dòng route; các API camera, incident, RFID/access và status vẫn chưa tách.

## v0.6.2-dev.24.11

- Tách ba endpoint hiệu chuẩn Spatial Mapping của camera USB sang `backend/app/routes/spatial_mapping.py`.
- Router nhận dependency qua service provider; không import ngược `main.py`.
- Giữ nguyên đường dẫn API, phương thức HTTP, dependency admin và mã phản hồi dự kiến.

## v0.6.2-dev.24.12 — Incident & Alert Routes Extraction

- Tách các endpoint danh sách incident, ACK từng incident, ACK tất cả, tắt còi, danh sách alerts và ACK alert sang `backend/app/routes/incidents.py`.
- Router nhận DB session, quyền truy cập, UID masking, đồng hồ nghiệp vụ và các hàm trạng thái incident/alarm qua service provider; không import ngược `main.py`.
- Giữ nguyên đường dẫn, HTTP method, giới hạn truy vấn, quy tắc che UID và logic cập nhật trạng thái/còi.
- Giữ hai compatibility entry points `acknowledge_all_incidents()` và `silence_incident_sirens()` trong `main.py` cho test/tích hợp cũ; HTTP route dùng module mới.
- Không chuyển Incident lifecycle/event synchronization core trong lần này vì các hàm đó còn được camera event worker và Decision Engine integration sử dụng.

## v0.6.2-dev.24.13 — Card Registry Routes Extraction

- Tách `GET /api/cards` và `POST /api/cards` sang `backend/app/routes/cards.py`.
- Router nhận DB session, quyền admin, schema `CardCreate`, UID normalizer và đồng hồ nghiệp vụ qua service provider; không import ngược `main.py`.
- Giữ nguyên đường dẫn, HTTP method, truy vấn thẻ/quyền vùng/phiếu lấy hàng, kiểm tra zone và phản hồi lỗi UID trùng.
- Các API kiểm tra quyền, liên kết Track, RFID scan, cập nhật/xóa thẻ và device heartbeat chưa được chuyển trong release này.

## v0.6.2-dev.24.14 — Access Routes Extraction

- Tách `POST /api/access/check`, `POST /api/access/associate` và `GET /api/system/access-logs` sang `backend/app/routes/access.py`.
- Tách logic kiểm tra thẻ thành `check_access_impl()` để HTTP route và luồng tương thích `/api/rfid/scan` dùng chung một implementation, không tạo nhánh cấp quyền thứ hai.
- Router nhận DB session, admin dependency, UID normalizer, đồng hồ/múi giờ nghiệp vụ, detector provider và logger qua service provider; không import ngược `main.py`.
- Giữ `main.check_access()` làm compatibility entry point vì `/api/rfid/scan` gọi trực tiếp hàm này. Giữ nguyên transaction `BEGIN IMMEDIATE`, reset quota theo ngày, conditional quota increment, ghi access log và sự kiện từ chối.

## v0.6.2-dev.24.15

- Extracted `POST /api/device/heartbeat`, `GET /api/scans`, and `GET /api/rfid/last-unknown` into `backend/app/routes/devices.py`.
- Preserved route paths, response shapes, auth dependencies, UID masking, heartbeat alarm/siren semantics, and KHO.DOAN2 compatibility behavior.
- No Decision Engine or camera detection algorithm changes.

## v0.6.2-dev.24.16

- Extracted camera anti-theft, USB protection-zone, RFID entry-ROI, and pending RFID binding endpoints into `backend/app/routes/camera_config.py`.
- Preserved endpoint paths, request schemas, authorization dependencies, detector calls, and response payloads.

## v0.6.2-dev.24.17 — Card Mutation Routes Extraction

- Moved `PATCH /api/cards/{uid}` and `DELETE /api/cards/{uid}` into the existing `backend/app/routes/cards.py` module.
- Kept card lock/delete database behavior, detector authorization revocation, HTTP status codes, and error messages.
- Injected detector provider and logger from the application composition root; the route module does not import `main.py`.
- No Decision Engine, tracking, or camera pipeline changes.

## v0.6.2-dev.24.18 — Camera Status Routes Extraction

- Extracted `GET /api/health`, `GET /api/camera/status`, `GET /api/cameras/center`, and `GET /api/ai/explainability` into `backend/app/routes/camera_status.py`.
- Preserved endpoint paths, response fields, session requirements, health degradation behavior, and detector error handling.
- Detector and incident-status augmentation are injected from the application composition root. Camera stream/WebRTC lifecycle and event synchronization remain in `main.py`.

## v0.6.2-dev.24.19 — Telegram Admin Routes Extraction

- Extracted `GET /api/admin/telegram/status` and `POST /api/admin/telegram/retry/{chat_id}/{event_id}` into `backend/app/routes/telegram_admin.py`.
- Injected database session, admin authorization dependency, business clock, and epoch clock through the application composition root.
- Preserved Telegram outbox diagnostics, retry eligibility, retry state reset, audit-log write, response shape, and HTTP errors.
- Telegram delivery workers and retry scheduling remain unchanged.

## v0.6.2-dev.24.20 — RFID Scan Route Extraction

- Extracted `POST /api/rfid/scan` into `backend/app/routes/rfid.py`.
- Injected device-key authorization, shared access-check compatibility callback, UID normalization, database session, detector-module provider, business clock, alarm/siren status callbacks, and logger.
- Preserved camera-zone permission check, short-lived RFID ticket creation, missing-camera-permission event, fail-closed ticket behavior, and response fields.
- The existing `check_access()` compatibility entry point remains in `main.py`; Decision Engine, detector, and hardware behavior are unchanged.

## v0.6.2-dev.24.21 — Camera Event Query Routes Extraction

- Extracted `GET /api/camera/events` and `GET /api/incidents/{incident_id}/timeline` into `backend/app/routes/camera_events.py`.
- Preserved session authorization, query limit validation, database ordering, response fields, incident 404 behavior, and UID masking for non-admin sessions.
- Database session, session dependency, and UID masking are injected from the application composition root; the route module does not import `main.py`.
- Camera event synchronization and incident lifecycle/business logic remain unchanged in `main.py`.

## v0.6.2-dev.24.23 — USB Camera Event Sync Service Extraction

- Moved USB detector event persistence and incident routing into `backend/app/services/camera_event_sync.py`.
- Extracted idempotent `security_events` insertion, evidence metadata enrichment, incident classification/routing, and SAFE-state incident reconciliation behind injected dependencies.
- Kept `_sync_usb_camera_events()` and `_reconcile_open_incidents()` in `main.py` as compatibility entry points; the async worker and detector lifecycle remain in the composition root.
- No detector algorithm, Decision Engine policy, API route, or hardware behavior changes.

## 0.6.2-dev.24.24

- Extracted authenticated `GET /api/status` dashboard aggregation into `backend/app/routes/system_status.py`.
- Preserved the `main.integrated_status()` compatibility entry point and injected dependencies through the route service object.
- No Decision Engine, detector, tracking, or camera-event synchronization rules changed.

## 0.6.2-dev.24.25

- Extracted authenticated external camera event ingestion (`POST /api/events`) into `backend/app/routes/external_events.py`.
- Moved compatibility alert persistence and event interpretation into the route module, with database, time, policy thresholds, camera state, and alarm state supplied through an explicit service object.
- Preserved request schema validation, admin dependency, event payload shape, alert deduplication, and existing response fields.
- Kept `main._external_alert` as a compatibility bridge for existing integrations.

# v0.6.2-dev.24.26 — Incident Status Service Extraction

- Tách tổng hợp trạng thái Incident đang mở và bổ sung trạng thái Incident vào detector status sang `backend/app/services/incident_status.py`.
- Service nhận DB session factory, detector-state provider và wall-clock provider; không import `main.py`.
- `main.py` giữ `_incident_status()` và `_augment_detector_status()` làm compatibility entry points, đồng thời cập nhật provider để duy trì các điểm monkeypatch cũ.
- Không thay đổi API, schema phản hồi, Decision Engine hoặc quy tắc đóng Incident.

## Verification dev.24.26

- `python -m pytest -q`: 368 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed.
- `python -m compileall -q backend ai`: passed.
- Docker, camera vật lý, trình duyệt, Telegram live và ESP32 không được xác minh.

## v0.6.2-dev.24.27 — Camera Media Routes Extraction

- Extracted read-only camera media and viewer telemetry endpoints into `backend/app/routes/camera_media.py`: stream viewer status, Track thumbnail, USB heatmap, evidence JPEG, and raw snapshot.
- Preserved admin-query authorization, camera-start policy for heatmap/snapshot, UUID-only evidence filename validation, response media types/cache headers, and existing error handling.
- Detector, stream manager, camera-read guard, evidence directory, and logger are injected from the composition root. The route module does not import `main.py`.
- Left MJPEG/WebRTC negotiation, inside-camera proxy, and metadata WebSocket lifecycle in `main.py` because they own long-lived async resource cleanup and session handling.
- No detector algorithm, Decision Engine, tracking, or hardware behavior changes.

# v0.6.2-dev.24.28 — Camera Stream Lifecycle Routes Extraction

- Extracted authenticated USB MJPEG streaming, WebRTC offer negotiation/peer cleanup, camera-stream metadata WebSocket, and authenticated ESP32-CAM MJPEG proxy into `backend/app/routes/camera_streams.py`.
- The router receives app, detector, stream manager, session validation, auth dependencies, WebRTC factory, environment lookup, camera-read guard, and logger through an explicit service object. The module does not import `main.py`.
- Preserved compatibility handler names in `main.py` for tests and existing integrations.
- Kept the existing 15-second pending WebRTC peer expiry, session revalidation, stream-manager connect/disconnect accounting, upstream HTTPX cleanup, and fail-closed WebSocket behavior.
- No detector algorithm, Decision Engine, tracking, or hardware behavior changes.

# v0.6.2-dev.24.30 — Camera Event Worker Extraction

- Extracted the USB camera event polling loop into `backend/app/services/camera_event_worker.py`.
- `CameraEventSyncWorker` now owns polling cadence, batch size, background-thread dispatch, cancellation propagation, and per-iteration exception isolation.
- Detector access, event persistence, and incident reconciliation remain injected callbacks; the worker does not import `main.py` or make incident/Decision Engine decisions.
- Kept `main._camera_event_sync_worker()` as a compatibility entry point and retained the existing lifespan task startup/shutdown behavior.
- Added focused tests for normal polling order and detector failure handling.
- No API, detector algorithm, tracking, Decision Engine, or hardware behavior changes.

## Verification dev.24.30

- `python -m pytest -q`: 375 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed.
- `python -m compileall -q backend ai`: passed.
- Docker, physical cameras, browser UI, and live Telegram delivery were not verified.

## 0.6.2-dev.24.31

- Tách điều phối startup/shutdown FastAPI sang `services/application_lifecycle.py`.
- `main.py` giữ vai trò composition root, cung cấp dependency và giữ các điểm monkeypatch tương thích.
- Giữ thứ tự khởi tạo DB, AI tùy chọn, camera event worker, retention worker, Telegram và thứ tự shutdown hiện hành.

# v0.6.2-dev.24.32 — Detector State Reader Extraction

- Extracted detector alarm-state lookup and normalization into `backend/app/services/detector_state.py` (`DetectorStateReader`).
- The reader receives a detector provider by dependency injection; it does not import `main.py` or the AI package.
- Preserved the lazy AI import and `main._current_detector_state()` compatibility entry point.
- Preserved state semantics: anti-theft disabled => `DISARMED`; otherwise uppercase `alarm_state`; missing state/provider errors => `UNKNOWN`.
- Added focused tests for normalization, disarmed state, missing state, and provider failure.
- No API, Decision Engine, detector algorithm, tracking, or hardware behavior changes.

# v0.6.2-dev.24.33 — Alarm Level Resolver Extraction

- Extracted mapping from live detector state and incident latch to the public `off` / `warning` / `severe` / `unknown` alarm vocabulary into `backend/app/services/alarm_level.py`.
- `AlarmLevelResolver` receives detector and incident-status providers through dependency injection and logs detector-read failures before returning `unknown`.
- Kept `main.current_alarm_level()` as a compatibility bridge and refreshes providers at call time to preserve existing monkeypatch/integration behavior.
- Added focused tests for all supported state mappings, incident latch precedence, and detector-provider failure.
- No detector algorithm, Decision Engine, tracking, API route, or hardware behavior changes.

## Verification dev.24.33

- `python -m pytest -q`: 387 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Physical camera, Docker build, browser visual behavior, and live Telegram delivery were not verified.

# v0.6.2-dev.24.34 — Auxiliary Backend Services Extraction

- Extracted allowed-access scan aggregation into `services/access_statistics.py` (`AccessStatisticsService`), covering recent allowed scans and distinct allowed UIDs for the business day.
- Extracted deduplicated compatibility-alert persistence into `services/external_alert_store.py` (`ExternalAlertStore`).
- Wired `/api/events` through the injected alert-persistence service; kept the router's fallback behavior for standalone consumers that do not provide the new dependency.
- Kept `main._scans_recently_allowed()`, `main._scans_today_allowed()`, and `main._external_alert()` as compatibility bridges that refresh dependencies at call time.
- Added isolated tests for access statistics and duplicate suppression / acknowledgement behavior.
- No API schema, AI detector, tracking, Decision Engine, or hardware behavior changes.

## Verification dev.24.34

- `python -m pytest -q`: 389 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release archive validator: passed.
- Physical camera, Docker build, browser visual behavior, and live Telegram delivery were not verified.

# v0.6.2-dev.24.35 — Incident Command Service Extraction

- Tách nghiệp vụ ACK tất cả Incident đang mở và tắt còi Incident sang `backend/app/services/incident_commands.py` (`IncidentCommandService`).
- Router `/api/incidents/ack-all` và `/api/incidents/siren-off` chuyển tiếp qua service được inject; router giữ fallback tương thích cho trường hợp được khởi tạo độc lập không cung cấp command callbacks.
- `main.py` giữ `acknowledge_all_incidents()` và `silence_incident_sirens()` làm compatibility entry points, refresh DB/time/status callbacks trước khi gọi service để bảo toàn các điểm monkeypatch cũ.
- Giữ nguyên điều kiện cập nhật: ACK chỉ tác động Incident `OPEN` chưa ACK; tắt còi chỉ đặt `siren_until=0` cho Incident `OPEN` có còi đang bật. Hai thao tác vẫn độc lập.
- Bổ sung kiểm thử service cho số bản ghi thay đổi, trạng thái đóng không bị tác động và tính độc lập giữa ACK/còi.
- Không thay đổi API, schema DB, AI, tracking, Decision Engine hoặc firmware.

## Verification dev.24.35

- `python -m pytest -q`: 390 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release archive validator: chạy khi đóng gói.
- Camera vật lý, Docker, giao diện trình duyệt và Telegram live chưa được xác minh.

## 0.6.2-dev.24.36 — External Camera State Extraction

- Added `ExternalCameraState` service to own in-memory compatibility camera state and provide synchronized updates/snapshots.
- External event ingestion now delegates outside/inside state updates to the service.
- Preserved the legacy mutable `_external_camera_state` mapping for existing status consumers and integrations.
- No changes to AI detection, tracking, Decision Engine, database schema, or hardware/firmware.

## 0.6.2-dev.24.37 — Camera Access Policy Extraction

- Extracted the camera read/start authorization rule into `services/camera_access_policy.py` (`CameraAccessPolicy`).
- Preserved the existing policy: admin reads may start the detector; non-admin reads may only use an already-running detector and otherwise receive HTTP 503.
- Kept `main._ensure_camera_for_read()` as a compatibility bridge used by the existing camera media and stream routers.
- Added focused tests for admin, non-admin, already-running, and missing-role cases.
- No API contract, detector algorithm, tracking, Decision Engine, database, or hardware changes.

# v0.6.2-dev.24.40 — Incident Health Policy Extraction

- Tách phân loại loại Incident sức khỏe (`camera_outage` / `ai_health`) và chính sách đóng Incident khi camera/AI phục hồi sang `services/incident_health_policy.py` (`IncidentHealthPolicy`).
- `main.py` giữ `_health_incident_type()` và `_close_health_incidents()` làm compatibility bridges; `CameraEventSyncService` tiếp tục nhận callback như trước.
- `IncidentStore` chỉ còn phụ trách persistence primitives của Incident; không còn chứa quy tắc phân loại/đóng Health Incident.
- Giữ nguyên hành vi: `camera_recovered` chỉ đóng `camera_outage`; các sự kiện phục hồi sức khỏe khác đóng `camera_outage` và `ai_health`, không đóng `intrusion`.
- Bổ sung test phân loại và đóng Incident theo từng loại.
- Không thay đổi API, schema DB, detector, tracking, Decision Engine, frontend hoặc firmware.

## Verification dev.24.40

- Pending execution in this release.

# v0.6.2-dev.24.41 — Evidence Retention Service Extraction

- Tách nghiệp vụ quản lý vòng đời tệp bằng chứng khỏi `backend/app/retention.py` sang `backend/app/services/evidence_retention.py` (`EvidenceRetentionService`).
- Service mới sở hữu việc bảo vệ evidence đang được Incident OPEN tham chiếu, dọn tệp theo tuổi/dung lượng và cập nhật metadata hết hạn trong `security_events` / `incident_events`.
- `RetentionService` giữ nguyên các phương thức `prune_evidence_files()` và `mark_evidence_expired()` làm compatibility delegates; chu kỳ dọn log và worker vẫn giữ nguyên.
- Không thay đổi API, schema DB, detector, tracking, Decision Engine, frontend hoặc firmware.

## Verification dev.24.41

- `python -m pytest -q`: 404 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release archive validator: pending packaging.

# v0.6.2-dev.24.42 — Audit Retention Service Extraction

- Tách nghiệp vụ dọn dữ liệu lịch sử khỏi `backend/app/retention.py` sang `services/audit_retention.py` (`AuditRetentionService`).
- Service mới xử lý thời hạn lưu trữ access logs, security events, system access logs và Incident đã đóng; tiếp tục bảo vệ các sự kiện còn công việc Telegram pending.
- `RetentionService.prune_old_logs()` giữ vai trò điều phối, kết hợp kết quả dọn audit records với `EvidenceRetentionService`; giữ nguyên cấu trúc kết quả trả về và worker theo giờ.
- Không thay đổi API, schema DB, detector, tracking, Decision Engine, frontend hoặc firmware.

## Verification dev.24.42

- `python -m pytest -q`: 404 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: pending.
- `python -m compileall -q backend ai`: pending.
- Release archive validator: pending packaging.

# v0.6.2-dev.24.43 — Retention Worker Extraction

- Tách vòng lặp chạy nền và xử lý lỗi của tác vụ retention khỏi `backend/app/retention.py` sang `services/retention_worker.py` (`RetentionWorker`).
- `RetentionService` tiếp tục điều phối hai chính sách audit/evidence và ủy quyền lịch chạy theo giờ cho worker; giữ nguyên thời gian chờ 60 phút, log khi có access/security records bị xóa và cô lập lỗi mỗi chu kỳ.
- Bổ sung test cho chu kỳ prune, log kết quả và hành vi cô lập lỗi/huỷ task.
- Không thay đổi API, schema DB, chính sách retention, detector, tracking, Decision Engine, frontend hoặc firmware.

## Verification dev.24.43

- `python -m pytest -q`: 406 passed, 1 warning (Starlette TestClient cookie deprecation).
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release archive validator: pending packaging.

# v0.6.2-dev.24.45 — Incident Lifecycle Service Extraction

- Tách nghiệp vụ mở/tái mở Incident và đóng intrusion Incident khi detector SAFE + đã được admin ACK khỏi `IncidentStore` sang `services/incident_lifecycle.py` (`IncidentLifecycleService`).
- `IncidentStore` giữ vai trò facade, tiếp tục cung cấp `open_incident()` và `close_resolved()` để bảo toàn các điểm gọi hiện tại; event persistence vẫn thuộc `IncidentEventStore`.
- Giữ nguyên SQL, cooldown, điều kiện bật còi, session matching và điều kiện đóng Incident; không thay đổi API hoặc schema DB.
- Bổ sung unit test xác nhận không đóng khi detector chưa SAFE và chỉ đóng intrusion OPEN đã ACK khi SAFE.

## v0.6.2-dev.24.46 — Incident Query & Alert Command Extraction

- Extracted incident and alert read queries into `IncidentQueryService`.
- Extracted individual security-alert acknowledgement into `IncidentAlertCommandService`.
- Kept route authorization, endpoint paths, response formats, and standalone-router compatibility fallbacks.
- Added focused tests for incident query mapping and alert acknowledgement / 404 behavior.

# v0.6.2-dev.24.48 — Incident & Security Alert Router Split

- Tách router Incident thành `routes/incident_records.py` (danh sách Incident, xác nhận Incident, xác nhận tất cả và tắt còi) và `routes/security_alerts.py` (truy vấn cảnh báo, xác nhận cảnh báo).
- `routes/incidents.py` được giữ làm compatibility facade, ghép hai router con để bảo toàn factory cũ và cách đăng ký trong `main.py`.
- Giữ nguyên endpoint, HTTP method, dependency xác thực, query parameters, response shape và nhánh fallback cho standalone router consumers.
- Không thay đổi schema DB, logic AI, tracking, Decision Engine, frontend hoặc firmware.

## v0.6.2-dev.24.49 — Camera Event and Incident Timeline Route Split

- Tách endpoint đọc sự kiện camera USB thành `routes/camera_event_feed.py`.
- Tách endpoint dòng thời gian Incident thành `routes/incident_timeline.py`.
- Giữ `routes/camera_events.py` làm compatibility facade để bảo toàn route factory cũ và các điểm gọi hiện tại.
- Không thay đổi URL, HTTP method, dependency xác thực hoặc cấu trúc dữ liệu phản hồi.
- Bổ sung kiểm thử cho hai router độc lập và facade tương thích.

## v0.6.2-dev.24.50 — Camera Media Route Split

- Tách nhóm API ảnh khung hình/telemetry camera sang `routes/camera_frames.py`: trạng thái viewer, thumbnail Track, heatmap và snapshot USB.
- Tách endpoint đọc ảnh bằng chứng UUID JPEG sang `routes/camera_evidence.py`; tiếp tục kiểm tra tên file theo định dạng UUID trước khi truy cập thư mục evidence.
- Giữ `routes/camera_media.py` làm compatibility facade, ghép hai router mới để bảo toàn cách đăng ký trong `main.py`.
- Giữ nguyên URL, HTTP method, xác thực admin, cache-control, cách xử lý lỗi và dữ liệu phản hồi.
- Không thay đổi AI, tracking, Decision Engine, schema DB, frontend hoặc firmware.

## Verification dev.24.50

- `python -m pytest -q`: 419 passed, 1 warning.
- `node --test tests/*.js tests/*.mjs`: 9 passed, 0 failed.
- `python -m compileall -q backend ai`: passed.
- Release ZIP validator: pending packaging.
- Chưa xác minh Docker, camera vật lý, giao diện trình duyệt và Telegram live.

## v0.6.2-dev.24.55 — Database Layer Split

- Tách vòng đời kết nối SQLite (`connect_db`, `db_session`) sang `backend/app/sqlite_connection.py`.
- Tách tạo bảng/chỉ mục hiện hành sang `backend/app/schema_tables.py`.
- Tách migration tiến về phía trước và bootstrap admin sang `backend/app/schema_migrations.py`.
- `backend/app/database.py` được thu gọn thành facade khởi tạo DB; tiếp tục export `connect_db`, `db_session`, `initialize_database` để giữ tương thích import hiện có.
- Giữ nguyên câu lệnh SQL, migration ID, điều kiện bootstrap và hành vi transaction hiện tại; không thay đổi schema nghiệp vụ, AI, tracking, API, frontend hoặc firmware.
- Bổ sung kiểm thử tính tương thích facade, khởi tạo lặp lại và bảo toàn dữ liệu hiện có.

## v0.6.2-dev.24.57 — API Schema Domain Split

- Tách các Pydantic model cho thẻ/RFID/truy cập sang `schemas_access.py`.
- Tách cấu hình camera và hiệu chuẩn không gian sang `schemas_camera.py`.
- Tách payload sự kiện an ninh sang `schemas_events.py`.
- Tách đăng nhập và quản trị tài khoản sang `schemas_admin.py`.
- Giữ `schemas.py` làm compatibility facade, bảo toàn tên import và class identity cho các consumer hiện tại.
- Không thay đổi endpoint, field, validator, default, ràng buộc dữ liệu, database, AI, frontend hoặc firmware.

## v0.6.2-dev.24.60 — Telegram Configuration and Lease Split

- Tách cấu hình Telegram (`TelegramConfig`, `TelegramContext`, `telegram_enabled`, `load_config`) sang `telegram/config.py`.
- Tách chính sách heartbeat/gia hạn distributed lease sang `telegram/lease.py`.
- Giữ `telegram/bot.py` làm adapter facade và worker supervisor; tiếp tục re-export các symbol cũ để bảo toàn import từ `telegram.bot`.
- Không thay đổi cách đọc biến môi trường, allowlist, ngưỡng cấu hình, thời hạn lease, retry/backoff hoặc vòng đời Telegram worker.
- Không thay đổi API Telegram, database, AI, tracking, Decision Engine, frontend hoặc firmware.

## v0.6.2-dev.24.61 — Device Authentication Split

- Tách xác thực `KHOAI_API_KEY`, kiểm tra độ mạnh khóa thiết bị và giới hạn số lần xác thực sai theo IP sang `backend/app/device_auth.py`.
- `backend/app/auth.py` tiếp tục re-export dependency và các symbol liên quan để bảo toàn import path hiện tại.
- Giữ nguyên header `X-API-Key`, mã HTTP 401/429/503, ngưỡng mặc định và hành vi fail-closed.
- Không thay đổi xác thực phiên admin, endpoint, database, AI, tracking, frontend hoặc firmware.

## v0.6.2-dev.24.65 — Pylance Typing Cleanup

- Bổ sung kiểu callable tường minh cho các provider database có thể chưa được cấu hình.
- Khai báo rõ hợp đồng Protocol cho service bundle của Auth, History và Spatial Mapping tại composition root.
- Bảo vệ trạng thái khởi tạo IncidentStore bằng accessor có kiểm tra invariant.
- Dùng handle WebRTC không nullable bên trong callback; giữ biến nullable riêng cho nhánh cleanup khi lỗi.
- Không thay đổi API, schema DB, chính sách xác thực, AI, tracking, Decision Engine, frontend hoặc firmware.

## v0.6.2-dev.24.66 — FastAPI Route Inspection Compatibility

- Bổ sung helper kiểm tra route tương thích giữa FastAPI dùng danh sách route đã expand và FastAPI trì hoãn router inclusion qua `_IncludedRouter`.
- Cập nhật các test kiểm tra endpoint HTTP/WebSocket và compatibility facade để duyệt route thực, không giả định mọi phần tử `app.routes` đều có thuộc tính `path`.
- Không thay đổi runtime backend, endpoint, frontend, database, AI, tracking, Decision Engine hoặc firmware.
