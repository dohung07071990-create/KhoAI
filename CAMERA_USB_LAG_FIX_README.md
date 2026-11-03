# KhoAI — bản tổng hợp camera USB và đánh giá hành vi

## Đã cập nhật trong bản này
- Tách luồng đọc camera, suy luận YOLO/ByteTrack và render MJPEG thành các worker riêng.
- MJPEG render mặc định 20 FPS, JPEG quality 74; cấu hình bằng `KHOAI_STREAM_FPS` (8–30) và `KHOAI_STREAM_JPEG_QUALITY` (55–90).
- Giữ kết quả nhận diện gần nhất trên hình video; khi AI chậm, bounding box/ID có thể cũ hơn nền video.
- Giữ logic vùng bảo vệ, cảnh báo, sự kiện, heatmap và ảnh bằng chứng hiện có.
- Thêm `ai/behavior_analyzer.py` để đối chiếu nhãn hành động với quyền, khu vực và lệnh công việc.
- Thêm `ai/action_policy.json.example` và tài liệu lộ trình nhận diện hành động.

## Chưa được triển khai / không được hiểu nhầm
- Chưa có mô hình action-recognition được huấn luyện và tích hợp để tự nhận diện hành động phức tạp từ video.
- Chưa có bộ dữ liệu gán nhãn riêng cho môi trường kho.
- `behavior_analyzer.py` chỉ đánh giá kết quả từ một mô hình nhận diện hành động khác; nó không đọc video và không tự nhận diện hành động.
- Chưa thể xác nhận độ chính xác hoặc FPS thực tế trên máy tính/webcam của người dùng.

## Phạm vi giữ nguyên
Bản này tập trung camera USB ngoài và backend/web liên quan. Firmware `esp32_access` (RFID/servo/còi) và `esp32_cam` được giữ nguyên, không thêm chức năng AI vào ESP32-CAM.

## Kiểm tra trong môi trường đóng gói
- `python -m compileall -q ai backend tests`: đạt.
- `node --check frontend/app.js`: đạt.
- `python tests/test_detector_logic.py`: đạt.
- `python -m pytest -q`: 5 passed.
- Chưa kiểm thử webcam vật lý và chưa benchmark trên máy triển khai.
