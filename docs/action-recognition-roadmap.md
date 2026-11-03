# Nhận diện hành động và đánh giá hành vi — KhoAI

## Phần đã có trong bản này
- YOLOv8n + ByteTrack: phát hiện người và theo dõi ID tạm thời.
- Vùng bảo vệ, cảnh báo xâm nhập, sự kiện và ảnh bằng chứng.
- `ai/behavior_analyzer.py`: đánh giá nhãn hành động do mô hình ngoài cung cấp, kết hợp quyền, khu vực và lệnh công việc.
- `ai/action_policy.json.example`: ví dụ quy tắc để tùy chỉnh.

## Giới hạn cần đọc
Bản này **chưa có mô hình nhận diện hành động video đã huấn luyện và chưa tự suy ra hành động từ camera**. `behavior_analyzer.py` chỉ đánh giá nhãn + độ tin cậy do một action-recognition model khác cung cấp. Các nhãn trong file mẫu là ví dụ cấu hình, không phải năng lực đã được kiểm chứng.

## Để hoàn thiện nhận diện hành động
1. Chốt danh sách hành động và định nghĩa từng lớp (lấy hàng, đặt hàng, trèo, ngã, đánh nhau...).
2. Thu thập video đại diện nhiều góc máy, ánh sáng, che khuất và cả tình huống bình thường/bất thường.
3. Gán nhãn clip/đoạn thời gian; chia train/validation/test theo video hoặc phiên ghi.
4. Chọn mô hình video action recognition hoặc pose-based phù hợp phần cứng; benchmark trên camera thật.
5. Nối đầu ra mô hình vào `evaluate_behavior()` sau khi đánh giá precision/recall và ngưỡng cảnh báo.
6. Lấy quyền người từ nguồn xác thực (RFID/phiên đăng nhập/phân quyền), lệnh công việc từ dữ liệu nghiệp vụ. Track ID ByteTrack không phải danh tính người.

## Nguyên tắc
- Thiếu nhãn, độ tin cậy thấp hoặc thiếu ngữ cảnh => `REVIEW`, không tự động duyệt.
- Không dùng một tư thế đơn lẻ để kết luận ý định trộm cắp.
- Cảnh báo AI cần người kiểm tra; không tự động mở khóa/điều khiển phần cứng từ suy luận hành vi.
- Phạm vi camera USB ngoài; không thay đổi firmware ESP32-RFID hoặc ESP32-CAM.
