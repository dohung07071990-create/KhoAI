# Phác thảo mô hình nhà kho nhỏ

Bản hướng dẫn này giúp bắt đầu dựng một mô hình học tập; kích thước có thể thay đổi theo vật liệu sẵn có. Gợi ý đế 40 × 30 cm, tường cao khoảng 10–15 cm, dùng foam board/bìa carton dày. Chưa có mô hình vật lý nào được lắp trong phiên làm việc này.

## Nhìn từ trên xuống

```text
                    MẶT SAU
┌──────────────────────────────────────────────┐
│ [ESP32-CAM]  ↘ góc nhìn toàn kho             │
│                                              │
│  ┌─────────┐        ┌────────────┐            │
│  │ Kệ hàng │        │  VÙNG CẤM  │  [USB cam]│
│  └─────────┘        └────────────┘   ↙       │
│                                              │
│  ┌────────────────┐                          │
│  │ ESP32 + mạch    │──dây tín hiệu──[servo]  │
│  │ đặt ngoài vách │                  │       │
│  └────────────────┘              ┌───┴────┐  │
│  [RC522 ngoài cửa]  → người vào → │ CỬA   │  │
└───────────────────────────────────┴───────┴──┘
                    MẶT TRƯỚC
```

## Lắp theo thứ tự

1. Cắt đế và dựng ba vách; để mặt trước có cửa mở được. Dùng bản lề giấy/băng dính vải để cửa xoay tự do.
2. Gắn servo cạnh cửa; nối càng servo với thanh đẩy hoặc chốt nhẹ. Thử đóng/mở bằng tay trước khi cấp điện, không để cơ cấu kẹt.
3. Đặt RC522 ở bên ngoài cạnh cửa để quẹt thẻ; đặt ESP32 trong hộp/giá cách xa vùng có thể chạm trực tiếp vào dây nguồn.
4. Gắn camera nhìn chéo từ góc trên. Vùng cấm có thể đánh dấu bằng băng dính màu trên sàn; điều chỉnh polygon trong `ai/person_detector.py` theo vị trí đó.
5. Đặt ESP32-CAM ở góc sau để quan sát bên trong kho; hướng ống kính tránh đèn chiếu thẳng gây lóa.
6. Đi dây gọn dọc theo vách, cố định bằng kẹp; thử từng phần ở điện áp thấp trước khi ghép toàn bộ.

## Ghi chú nguồn và an toàn

- **RC522 chỉ cấp 3.3 V; không nối 5 V.** Chân GND RC522 và ESP32 phải chung.
- Servo thường cần nguồn DC riêng đúng thông số của servo. Không cấp servo từ chân 3V3; nối chung GND nguồn servo với GND ESP32 để tín hiệu điều khiển có mốc chung.
- Còi chủ động trong sketch mẫu dùng GPIO27. Nếu còi/module tiêu thụ dòng lớn hơn mức GPIO cho phép, dùng transistor/driver phù hợp thay vì kéo trực tiếp từ chân GPIO.
- Không gắn lưỡi cắt/chốt kim loại sắc; không để dây hở. Mô hình chỉ để trình diễn, không thay khóa cửa thật.
