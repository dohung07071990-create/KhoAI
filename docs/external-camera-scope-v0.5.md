# KhoAI v0.5.0 — External USB Camera Security

## Phạm vi

Phiên bản này chỉ phát triển pipeline AI cho camera USB đặt bên ngoài nhà kho. ESP32-CAM và xử lý hình ảnh bên trong nhà kho được loại khỏi phạm vi AI hiện tại; mã firmware và các chức năng tích hợp khác được giữ nguyên, không xóa.

## Pipeline

`USB Camera -> OpenCV -> YOLOv8n (class person) -> ByteTrack -> Foot Point -> Zone Manager -> Alarm Manager -> Event/Evidence -> Web Dashboard`

YOLO/ByteTrack chạy trên máy tính chạy backend, không chạy trên ESP32-CAM. Track ID là định danh tạm thời trong một luồng camera, không phải danh tính nhân viên.

## Nâng cấp v0.5.0

- Camera status trả thêm `camera_role: external_usb` và `camera_health: online|offline`.
- Khi không mở được camera hoặc mất tín hiệu liên tục đủ ngưỡng reconnect, tạo một sự kiện `camera_offline`.
- Khi camera kết nối lại sau trạng thái offline, tạo một sự kiện `camera_recovered`.
- Không lặp sự kiện offline trong lúc hệ thống tiếp tục thử kết nối.
- Sự kiện camera offline/recovered có `track_id=-1`, `camera_role=external_usb`; không có ảnh bằng chứng nếu không có frame.

## Chưa triển khai trong phiên bản này

- Chưa tự đặt polygon theo mặt bằng kho: vùng phải được người vận hành vẽ trên khung hình camera USB thực tế.
- Chưa xác định danh tính người chỉ từ Track ID.
- Chưa nhận diện hành vi trộm cắp/phá hoại hoặc tự đếm hàng hóa.
- Chưa xác minh góc nhìn camera, vùng mù, độ chính xác ban ngày/ban đêm trên thiết bị thật.
- Chưa thay đổi logic RFID/ESP32 hoặc điều khiển cửa.

## Cấu hình và kiểm tra

1. Kết nối camera USB với máy chạy backend.
2. Chạy `python -m ai.list_cameras` để tìm index.
3. Đặt `CAMERA_INDEX` trong `.env` hoặc dùng `auto`.
4. Chạy backend và mở tab Camera ngoài.
5. Vẽ vùng bảo vệ theo mặt sàn/khu vực tiếp cận cần giám sát trên hình camera thực tế.
6. Thử ngắt và kết nối lại camera để kiểm tra hai sự kiện `camera_offline` và `camera_recovered`.

Kiểm thử tự động không thay thế kiểm thử camera thật.
