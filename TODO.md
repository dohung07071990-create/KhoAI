# TODO – Kho AI

## 1. API kiểm soát ra vào và lịch sử
- [x] Dùng FastAPI và SQLite; đã khởi chạy API tại cổng 3000.
- [x] Có hai bảng chính: thẻ và lịch sử quẹt, lưu ai, thời điểm và kết quả.
- [x] Nhận UID, kiểm tra thẻ có hợp lệ không, trả “cho phép” hoặc “từ chối” và ghi lịch sử; curl đã kiểm tra cả UID hợp lệ lẫn UID chưa cấp.
- [x] Có thể kiểm thử API bằng curl hoặc Postman khi chưa kết nối mạch; ví dụ curl nằm trong README.

## 2. Giao diện giám sát và cấp thẻ
- [x] Có bản phác thảo giao diện gồm trang xem camera, trang lịch sử và trang cấp thẻ.
- [x] Làm web HTML/CSS/JavaScript để xem camera và hiển thị bảng lịch sử; API đã trả HTML/JavaScript qua HTTP.
- [x] Có form cấp thẻ cơ bản với tên người và tuổi; thêm UID để định danh thẻ.

## 3. AI nhận diện người và camera
- [x] Dùng Python cùng ultralytics và opencv-python; các thư viện đã cài/import được trong virtualenv dự án.
- [x] Dùng YOLO có sẵn để nhận diện “người”, không tự huấn luyện.
- [x] Vẽ vùng cấm trên hình, cảnh báo khi người bước vào vùng; có cảnh báo log và trạng thái cảnh báo trên dashboard.
- [x] Có endpoint stream camera lên web; camera USB thật chưa được nối trong môi trường này.
- [ ] Thử nhận diện, hiển thị hình và cảnh báo trực tiếp bằng camera USB trên máy có webcam.

## 4. Firmware ESP32, RC522, servo, còi và ESP32-CAM
- [x] Có code đọc UID, in ra màn hình và gửi UID lên API; kết quả cho phép mở servo, từ chối kêu còi; lỗi kết nối giữ cửa đóng.
- [x] Có sơ đồ/hướng dẫn RC522 chỉ dùng 3.3V, không cấp 5V; servo dùng nguồn phù hợp và chung GND.
- [x] Có sketch ESP32-CAM AI Thinker phát luồng MJPEG và hướng dẫn nạp.
- [ ] Biên dịch, nạp và thử thực tế với ESP32, RC522, servo, còi và ESP32-CAM; chưa có mạch trong môi trường này.

## 5. Mô hình nhà kho nhỏ
- [x] Có bản phác thảo và hướng dẫn vị trí cửa, camera, RC522, ESP32, servo và dây nguồn.
- [ ] Dựng mô hình vật lý nhà kho nhỏ; việc này cần vật liệu và thao tác ngoài đời.
