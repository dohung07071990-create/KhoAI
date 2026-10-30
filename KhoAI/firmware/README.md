# Firmware ESP32: kiểm soát thẻ và ESP32-CAM

Thư mục gồm hai sketch Arduino độc lập. Cả hai chứa placeholder Wi‑Fi; sketch kiểm soát thẻ còn có placeholder IP máy chủ API. Hãy tự cấu hình trước khi nạp. Không đặt mật khẩu/token hay thông tin nhạy cảm trong mã được chia sẻ.

## 1. ESP32 + MFRC522: kiểm tra quyền truy cập

### Kết nối

| MFRC522 | ESP32 |
|---|---:|
| 3.3V | 3V3 |
| GND | GND |
| SDA / SS | GPIO5 |
| SCK | GPIO18 |
| MOSI | GPIO23 |
| MISO | GPIO19 |
| RST | GPIO22 |
| IRQ | Không nối |

**MFRC522 chỉ dùng logic/nguồn 3.3 V — không cấp 5 V.** Đặt SS/SDA, SCK, MOSI, MISO, RST đúng như bảng (VSPI mặc định). Còi chủ động nối tín hiệu với GPIO27 và GND; sketch giả định còi kêu khi chân ở mức HIGH. Kiểm tra giới hạn dòng và cực tính theo module còi.

Servo nối tín hiệu vào GPIO13. **Servo cần nguồn phù hợp với loại servo; không cấp nguồn servo từ chân 3V3 của ESP32.** Nối chung GND nguồn servo với GND ESP32 để có mốc tín hiệu chung. Dòng khởi động servo có thể làm ESP32 sụt áp/reset; chọn nguồn và cách đấu dây phù hợp.

### Thư viện

Cài trong Arduino IDE Library Manager:

- **MFRC522** (Miguel Balboa / GithubCommunity).
- **ArduinoJson** (Benoit Blanchon; ArduinoJson 6 trở lên).
- **ESP32Servo**.

`WiFi`, `HTTPClient`, `SPI` đi kèm Arduino-ESP32 core. Chọn board ESP32 phù hợp với module của bạn và cổng serial tương ứng.

### Cấu hình và hành vi

Mở `esp32_access/esp32_access.ino`, điền `WIFI_SSID`, `WIFI_PASSWORD` và `SERVER_IP` ở đầu file. IP phải là địa chỉ máy chạy API có thể truy cập từ cùng mạng; endpoint được tạo thành `http://<SERVER_IP>:3000/api/access/check`.

Khi quét thẻ, sketch gửi POST với `Content-Type: application/json` và body như `{"uid":"04A1B2C3"}` (UID hex viết hoa, mỗi byte đủ hai ký tự). API cần trả JSON có trường boolean, ví dụ `{"allowed":true}` hoặc `{"allowed":false}`. `allowed: true` mở servo góc 90° trong 2 giây rồi đưa về góc đóng 0°; `false` kêu còi ngắn. Nếu Wi‑Fi/API lỗi, mã **fail-closed**: không mở servo. Có thể chỉnh góc servo theo cơ cấu thực tế.

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
