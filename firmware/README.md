# Firmware ESP32: kiểm soát thẻ và ESP32-CAM

Thư mục gồm hai sketch Arduino độc lập. Cả hai chứa placeholder Wi‑Fi; sketch kiểm soát thẻ còn có placeholder IP máy chủ API. Hãy tự cấu hình trước khi nạp. Không đặt mật khẩu/token hay thông tin nhạy cảm trong mã được chia sẻ.

## 1. ESP32 + MFRC522: kiểm tra quyền truy cập

### Kết nối

| MFRC522  |     ESP32 |
| -------- | --------: |
| 3.3V     |       3V3 |
| GND      |       GND |
| SDA / SS |     GPIO5 |
| SCK      |    GPIO18 |
| MOSI     |    GPIO23 |
| MISO     |    GPIO19 |
| RST      |    GPIO22 |
| IRQ      | Không nối |

**MFRC522 chỉ dùng logic/nguồn 3.3 V — không cấp 5 V.** Đặt SS/SDA, SCK, MOSI, MISO, RST đúng như bảng (VSPI mặc định). Còi chủ động nối tín hiệu với GPIO27 và GND; sketch giả định còi kêu khi chân ở mức HIGH. Kiểm tra giới hạn dòng và cực tính theo module còi.

Servo nối tín hiệu vào GPIO13. **Servo cần nguồn phù hợp với loại servo; không cấp nguồn servo từ chân 3V3 của ESP32.** Nối chung GND nguồn servo với GND ESP32 để có mốc tín hiệu chung. Dòng khởi động servo có thể làm ESP32 sụt áp/reset; chọn nguồn và cách đấu dây phù hợp.

### Thư viện

Cài trong Arduino IDE Library Manager:

- **MFRC522** (Miguel Balboa / GithubCommunity).
- **ArduinoJson** (Benoit Blanchon; ArduinoJson 6 trở lên).
- **ESP32Servo**.

`WiFi`, `HTTPClient`, `SPI` đi kèm Arduino-ESP32 core. Chọn board ESP32 phù hợp với module của bạn và cổng serial tương ứng.

### Cấu hình và hành vi

Mở `esp32_access/esp32_access.ino`, điền `WIFI_SSID` và `WIFI_PASSWORD` tại đầu file; không ghi thông tin Wi‑Fi thật vào bản mã chia sẻ. Đặt `serverIp` tới máy chạy KhoAI. `SERVER_PORT` mặc định là `3000` theo cấu hình hiện tại; nếu backend chạy cổng khác, sửa hằng số này trước khi nạp. Endpoint là `/api/rfid/scan`.

Đặt `DEVICE_ID` trùng với tên thiết bị trong `KHOAI_DEVICE_API_KEYS_JSON` (hiện mặc định `gate01`). Sinh API key riêng tối thiểu 32 ký tự, cấu hình vào registry trên backend và nhập vào Serial Monitor bằng `key <key>` hoặc `cfg <ip> <key>`. Key được lưu trong NVS và chỉ hiện bốn ký tự cuối khi dùng lệnh `show`. Firmware gửi `X-API-Key`, `X-Device-ID` và body `{"uid":"04A1B2C3","device_id":"gate01"}`. Backend trả trường boolean `allow`; chỉ `allow: true` mới mở servo. Lần quẹt trùng trong cửa sổ debounce được trả `allow: false`, không trừ quota và không mở cửa lần nữa.

Servo mở góc 90° trong 2 giây rồi về góc đóng 0°; khi bị từ chối, còi/LED đỏ báo trạng thái. Mất Wi‑Fi, thiếu/sai key hoặc lỗi API đều **fail-closed**: không mở servo. Có thể chỉnh góc và thời lượng theo cơ cấu thực tế.

Serial Monitor: **115200 baud**; in UID và kết quả hoặc lỗi API.

Kết nối Wi‑Fi trong lúc khởi động có timeout 10 giây; nếu chưa có Wi‑Fi, đầu đọc vẫn khởi động và firmware thử kết nối lại định kỳ. Khi chưa liên lạc được server, cửa giữ đóng (fail-closed).

## 2. ESP32-CAM AI Thinker: MJPEG cơ bản

Mở `esp32_cam/esp32_cam.ino` và điền placeholder `WIFI_SSID`, `WIFI_PASSWORD`. Sketch dùng pin map AI Thinker, camera JPEG và HTTP server tích hợp trong Arduino-ESP32; không cần thư viện Arduino bên ngoài. Sau khi kết nối Wi‑Fi, địa chỉ IP được in trên Serial Monitor:

- Trang xem: `http://<ESP32-CAM-IP>/`
- Luồng MJPEG: `http://<ESP32-CAM-IP>:81/stream`

Thiết bị xem phải truy cập được IP của ESP32-CAM trên cùng mạng. Bản sketch này chỉ cung cấp stream cơ bản, không có xác thực hoặc mã hóa; không công khai lên Internet nếu chưa bổ sung biện pháp bảo vệ.

## Chọn board và nạp

1. Cài **esp32 by Espressif Systems** trong Arduino IDE Boards Manager.
2. Mở đúng file `.ino` tương ứng. Với sketch truy cập thẻ, cài các thư viện liệt kê ở trên.
3. Với camera, vào **Tools → Board → esp32 → AI Thinker ESP32-CAM** (tên có thể khác đôi chút theo phiên bản core). Với sketch MFRC522, chọn board ESP32 khớp phần cứng thực tế, ví dụ **ESP32 Dev Module**.
4. Chọn cổng serial đúng. Khi nạp ESP32-CAM trên nhiều board, cần đưa GPIO0 xuống GND để vào chế độ nạp; nhả GPIO0 khỏi GND rồi reset/khởi động lại sau khi nạp. Adapter USB-to-serial cần mức logic 3.3 V và nguồn ổn định theo yêu cầu module.
5. Mở Serial Monitor ở **115200 baud** để xem IP và trạng thái. Thử nghiệm phần cứng cẩn trọng, đặc biệt với servo và nguồn ngoài.

Đây là mã nguồn/hướng dẫn; chưa có tuyên bố đã nạp, chạy API thật hay kiểm thử phần cứng. Cần xác nhận tương thích thư viện, phiên bản Arduino-ESP32, đấu nối, nguồn và cơ cấu servo trên thiết bị thực tế.

## Firmware ESP32 tích hợp từ KHO.DOAN2

### ESP32 RFID

- Mở `esp32_access/esp32_access.ino` trong Arduino IDE; cài MFRC522, ArduinoJson v6/v7, ESP32Servo.
- Điền Wi-Fi SSID/password và đặt `serverIp`; kiểm tra `SERVER_PORT` khớp cổng server KhoAI (mặc định 3000).
- Nạp code, mở Serial Monitor 115200 baud; `show` xem cấu hình, `ip <IP>` đổi IP, `key <key>` đặt key.
- Mặc định firmware dùng HTTP để tương thích mạng LAN hiện có. Có thể bật HTTPS trong `esp32_access.ino` bằng `SERVER_USE_HTTPS = true`, điền CA PEM vào `SERVER_ROOT_CA`, và dùng chứng thư có SAN khớp `serverIp`; thiếu CA thì firmware từ chối kết nối. Không dùng chế độ bỏ qua xác minh chứng thư.
- Nếu tiếp tục dùng HTTP, chỉ triển khai trong VLAN/mạng thiết bị cô lập, chặn truy cập từ Wi-Fi khách và Internet, và chỉ cho phép thiết bị đi tới API server.
- Đặt API key ngẫu nhiên riêng tối thiểu 32 ký tự cho mỗi thiết bị. Có thể cấu hình `KHOAI_DEVICE_API_KEYS_JSON` dạng `{"gate01":"<key-random-32-ky-tu-tro-len>"}`; khóa ID phải khớp `DEVICE_ID` trong sketch. Firmware gửi `X-Device-ID` và `X-API-Key`. Nếu chưa bật registry theo thiết bị, server dùng tương thích ngược với `KHOAI_API_KEY` dùng chung.

### ESP32-CAM AI Thinker

- Mở `esp32_cam/esp32_cam.ino`; chọn board AI Thinker ESP32-CAM và điền Wi-Fi.
- Mở Serial Monitor để xem IP. Web stream là `http://<IP>:81/stream`, ảnh tĩnh `http://<IP>/capture`.
- Trong web KhoAI > Thiết lập thiết bị, nhập `http://<IP>:81` rồi lưu.
