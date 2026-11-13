# Dynamic Stream Manager — v0.6.2-dev.22

## Phạm vi

- Quản lý phiên người xem riêng cho từng nguồn `usb`, `inside` và kênh metadata.
- Ghi nhận số phiên đang xem, giao thức, tổng kết nối/ngắt kết nối, số frame và byte đã phân phối.
- MJPEG chỉ đăng ký phiên khi trình duyệt thực sự mở stream; phiên được giải phóng trong `finally` khi client ngắt.
- WebRTC được tính là một phiên phân phối và được giải phóng khi peer đóng, mất kết nối hoặc lỗi kết nối.
- ESP32-CAM proxy cũng có lifecycle và thống kê riêng.
- WebSocket `/ws/camera/streams` chỉ gửi metadata trạng thái mỗi giây; video vẫn đi qua MJPEG/WebRTC.
- API quản trị `GET /api/camera/streams/status` cung cấp snapshot thống kê.

## Ranh giới an toàn quan trọng

Không có người xem chỉ có nghĩa là không có client nhận video. Manager **không** dừng camera capture, YOLO, ByteTrack, event sync hoặc Decision Engine. Việc giữ pipeline an ninh độc lập với nhu cầu xem trực tiếp tránh bỏ lỡ sự kiện khi dashboard không mở.

## Giới hạn

- WebRTC vẫn là endpoint thử nghiệm, phụ thuộc `aiortc`/`av` và cấu hình mạng.
- Thống kê hiện là bộ đếm tiến trình, không phải số liệu bền vững qua lần khởi động backend.
- `last_frame_latency_ms` chỉ có giá trị khi upstream cung cấp phép đo phù hợp; không được suy diễn thành end-to-end latency.
- Không tự động hạ độ phân giải hoặc FPS của detector; thay đổi đó có thể ảnh hưởng pipeline AI và cần đánh giá riêng.
