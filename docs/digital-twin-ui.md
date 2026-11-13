# KhoAI Warehouse 3D & Analytics UI

## Thành phần
- `frontend/warehouse-twin.js`: sơ đồ kho 3D minh họa bằng Three.js; hỗ trợ kéo xoay.
- `frontend/warehouse-analytics.js`: biểu đồ Vizzu đọc thống kê từ `/api/stats`.
- `frontend/app.js`: trạng thái camera từ `/api/camera/status`, sự kiện từ `/api/camera/events`, trạng thái thiết bị từ `/api/status`, trạng thái backend từ `/api/health`.

## Quy tắc hiển thị trạng thái
- SAFE chỉ hiển thị khi dữ liệu có trạng thái tương ứng và `anti_theft_enabled` không phải false.
- `anti_theft_enabled=false` hiển thị DISABLED, màu xám.
- UNKNOWN hiển thị màu xám, không mặc định an toàn.
- Lỗi gọi `/api/camera/status` hiển thị OFFLINE, màu xám, bỏ số liệu realtime và hiển thị thời gian kể từ lần cập nhật cuối.

## Giới hạn mô hình
Sơ đồ 3D được dựng theo phác thảo nhà kho trong `docs/mo-hinh-nha-kho.md`; kích thước và tọa độ camera/kệ/vùng chưa được hiệu chuẩn với không gian vật lý. Khi chưa có calibration hợp lệ, Track chỉ hiển thị dưới dạng số lượng tín hiệu và không gán vị trí 3D giả. Khi calibration hợp lệ, dev.21 hiển thị marker tương đối theo miền điểm hiệu chuẩn; vị trí trên mô hình schematic chưa phải vị trí thực địa đã nghiệm thu. Vùng bảo vệ đổi màu theo trạng thái backend, không biểu diễn polygon camera như phép chiếu 3D đã hiệu chuẩn. Khi trình bày, gọi đây là **Sơ đồ kho 3D (minh họa)**, không gọi là Digital Twin đã hiệu chuẩn.

## Thư viện ngoài và giới hạn bảo mật
Three.js `0.170.0` và Vizzu `0.18` hiện được nạp từ jsDelivr. Vizzu có liên kết tham khảo tới https://vizzu.com/ mở tab mới theo chủ đích. Google Fonts đã được gỡ để tránh yêu cầu font bên ngoài.

**Việc còn mở:** chưa có bản Three.js/Vizzu vendor nội bộ được xác minh trong gói này. Vì vậy giao diện 3D/biểu đồ vẫn cần Internet; chưa áp dụng CSP chỉ cho phép `script-src 'self'`, chưa có SRI cho module import. Không được coi gói này là đã hoàn tất hardening chuỗi cung ứng thư viện.


### Ổn định kích thước khi chuyển trang
Mô hình 3D nằm trong trang Tổng quan, các trang khác được ẩn bằng thuộc tính `hidden`. Khi trang bị ẩn, kích thước đo được có thể bằng 0; bộ resize hiện bỏ qua kích thước này. Khi quay lại Tổng quan, sự kiện điều hướng kích hoạt đo lại sau khi trình duyệt hoàn tất bố cục. Canvas không còn `min-height` nội tại có thể làm thay đổi ngược kích thước stage.


### Bố cục nhà kho và vật thể lưu trữ

Mô hình 3D hiện sử dụng sơ đồ bốn phòng A–D, lối đi dọc/ngang, cửa phòng, lối vào RFID và khu vực ngoài theo bố cục người dùng cung cấp. Mỗi phòng có kệ, pallet và thùng hàng để thể hiện công năng kho. Các vị trí này là mô hình trực quan gần đúng, không phải bản vẽ thi công hay số đo đã khảo sát. Nhãn nổi được giới hạn ở tên phòng, vùng cấm ngoài và lối vào RFID. Trạng thái Track được hiển thị bằng badge màu trong danh sách theo dõi.


### Góc nhìn tổng quát
Camera phối cảnh được lùi ra xa và tăng FOV để ưu tiên nhìn trọn mặt bằng nhà kho, lối đi và khu vực ngoài trong một khung hình. Đây là điều chỉnh góc nhìn hiển thị, không thay đổi tọa độ hay tỷ lệ hình học của các phòng/kệ.

## Interactive camera controls
The warehouse model opens in a full-layout overview. Users can drag to orbit/tilt, use the wheel or +/- buttons to zoom, right-drag (or Shift+left-drag) to pan, and use the home button to restore the overview. Touch supports one-finger orbit and two-finger pinch zoom. These operations affect only the Three.js camera view; they do not alter AI zone coordinates or detector configuration.


## v0.6.2-dev.21 – Digital Twin Interpolation

- Digital Twin nhận `spatial_tracks` chỉ khi Homography có `valid=true`, đúng `camera_id` và `calibration_id`.
- Backend gắn `observed_at` theo thời điểm xử lý frame; không suy diễn timestamp từ thời điểm trình duyệt nhận phản hồi.
- Frontend nội suy vị trí marker bằng exponential smoothing; Track cũ mờ dần sau 8 giây và bị loại khỏi cảnh sau 15 giây.
- Khi calibration không hợp lệ hoặc backend offline, marker bị xóa; không giữ vị trí cũ như dữ liệu live.
- Tọa độ sàn được ánh xạ tương đối vào footprint của mô hình schematic theo miền điểm hiệu chuẩn. Đây không phải tọa độ 3D thực hoặc bằng chứng vị trí thực địa chính xác; mô hình vẫn được đánh dấu `SCHEMATIC · NOT TO SCALE`.
- Interpolation chỉ tác động lớp hiển thị, không thay đổi ByteTrack, Decision Engine, vùng cấm hoặc quyết định SAFE/WARNING/ALARM.
