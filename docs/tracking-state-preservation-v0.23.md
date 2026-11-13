# Tracking State Preservation — v0.6.2-dev.23.2

## Mục tiêu

Giữ ngữ cảnh Decision Engine trong cùng tiến trình qua một lần camera USB phục hồi ngắn, nhưng không xem Track ID hoặc vị trí hình học là danh tính.

## Chính sách

- `KHOAI_TRACK_STATE_PRESERVE_SECONDS` mặc định `3.0` giây và bị giới hạn tối đa `3.5` giây.
- Outage được tính từ timestamp của frame tốt cuối cùng (`_last_raw_at`), không tính từ thời điểm watchdog/capture loop báo lỗi muộn.
- Khi camera chuyển sang offline, mọi RFID ticket đang chờ và mọi quyền RFID gắn Track bị thu hồi ngay, kể cả outage ngắn. Sau khi camera phục hồi, người dùng phải quẹt thẻ lại.
- Decision Engine có thể giữ ngữ cảnh phiên trong outage ngắn; điều này không giữ hoặc chuyển quyền RFID.
- Quyền RFID không được chuyển từ Track ID cũ sang ID mới bằng IoU, khoảng cách hoặc vị trí. Track mới cần ticket RFID mới và thao tác liên kết hợp lệ.
- Gắn quyền yêu cầu đồng thời: ticket còn hạn, camera có frame mới, Track còn được nhìn thấy gần đây và thẻ có ít nhất một vùng được cấp. Kiểm tra và tiêu thụ ticket diễn ra trong cùng khóa detector.
- Ticket RFID có thời hạn tối đa 20 giây. Quyền gắn với Track có thời hạn tối đa 60 giây; quyền bị thu hồi nếu Track không được xác nhận trong hơn `KHOAI_RFID_TRACK_AUTH_LOSS_SECONDS` (mặc định 0.75 giây).
- `stop()` và đổi nguồn camera xóa ticket và quyền RFID.
- Outage dài hơn cửa sổ bảo toàn reset cả Track state và Decision Engine.

## API và audit

`/api/access/check` không thể gắn quyền nếu không có ticket RFID hợp lệ. `/api/access/associate` sử dụng cùng phương thức liên kết có kiểm tra Track/ticket bên trong detector, tránh khoảng hở giữa bước kiểm tra và bước cấp quyền.

`GET /api/camera/status` tiếp tục cung cấp `track_state_preservation`; sự kiện `camera_recovered` ghi chính sách và thời gian outage. Sự kiện `authorization_revoked` ghi lý do thu hồi.

## Ranh giới an toàn

Track ID không phải danh tính. Không có nhận diện người để chứng minh cùng một cá nhân sau khi Track biến mất. Vì vậy, khi camera mất tín hiệu hoặc Track không còn được xác nhận, hệ thống chọn thu hồi quyền thay vì suy đoán người xuất hiện tiếp theo là người cũ.

## Chưa xác minh

Chưa thử camera USB/ESP32-CAM vật lý, chưa kiểm tra ByteTrack ID reuse trong điều kiện nhà kho thật và chưa thử luồng RFID với ESP32/RC522 thật.
