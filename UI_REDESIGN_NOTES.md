# KhoAI UI redesign

## Nền tảng
- Giao diện responsive, dark enterprise security-console; giữ nguyên các ID điều khiển và tab data-t của frontend gốc.
- `app.js` tiếp tục đảm nhiệm gọi API, thao tác RFID, cảnh báo, ROI và đồng bộ camera.
- `warehouse-twin.js` dựng sơ đồ kho 3D minh họa; `warehouse-analytics.js` dựng biểu đồ Vizzu từ thống kê backend.

## Đồng bộ và an toàn trạng thái
- Trạng thái camera/AI/ByteTrack/FPS/Track lấy từ `/api/camera/status`.
- Backend lỗi: sơ đồ chuyển OFFLINE màu xám, xóa các số liệu realtime và hiển thị tuổi dữ liệu cuối cùng.
- Chống trộm tắt: vùng bảo vệ chuyển DISABLED màu xám; UNKNOWN không còn dùng vật liệu SAFE màu xanh.
- Chỉ báo backend được cập nhật từ `/api/health`; đồng hồ là giờ máy khách, không mang nghĩa trạng thái live.
- Sơ đồ 3D không định vị Track theo tọa độ không gian thực.

## Hiệu năng
- Vòng lặp dựng hình giới hạn tối đa 30 FPS, tạm dừng khi tab ẩn hoặc khu vực 3D ra khỏi viewport.
- Tôn trọng `prefers-reduced-motion`.

## Phụ thuộc ngoài
- Google Fonts đã được gỡ, dùng font hệ thống.
- Three.js và Vizzu hiện vẫn tải từ jsDelivr CDN; cần Internet. Chưa thể bật CSP `script-src 'self'` hoặc cam kết chạy offline khi chưa có bản vendor nội bộ đã xác minh. Không được xem phần hardening CDN/CSP là hoàn tất.
- Liên kết Vizzu trong phần analytics là liên kết tham khảo có chủ đích, mở website Vizzu ở tab mới.
