# KhoAI v0.4.0 — Zone Manager và Alarm Manager

## Quy tắc vùng

- `ai/zone.json` tiếp tục lưu đa giác chuẩn hóa gốc, dùng làm vùng ALARM ban ngày.
- 06:00–17:59 (Asia/Ho_Chi_Minh): hệ số vùng ALARM = 1,00.
- 18:00–05:59 (Asia/Ho_Chi_Minh): hệ số vùng ALARM = 1,15.
- Vùng WARNING được tạo bằng cách mở rộng vùng ALARM thêm hệ số 1,12 quanh trọng tâm đa giác.
- Tọa độ sau khi mở rộng được giới hạn trong khoảng 0–1. Đây là phép nới đa giác theo trọng tâm, không phải offset hình học chính xác theo khoảng cách mét.

## Quy tắc trạng thái

- `SAFE`: không có người trong vùng WARNING/ALARM hoặc hệ thống chống trộm đang tắt.
- `WARNING`: có ít nhất một người trong vùng WARNING nhưng chưa có người trong vùng ALARM.
- `ALARM`: có ít nhất một người đã được xác nhận trong vùng ALARM.
- Khi nhiều người xuất hiện đồng thời, ALARM ưu tiên hơn WARNING; WARNING ưu tiên hơn SAFE.
- Việc bật chống trộm đánh giá trạng thái track hiện tại. Người đã ở trong vùng ALARM trước lúc bật vẫn làm hệ thống chuyển ALARM.
- Công tắc chống trộm không thay đổi lịch ngày/đêm hoặc hình học vùng.

## API

`PUT /api/camera/anti-theft`

```json
{"enabled": true}
```

Phản hồi gồm `anti_theft_enabled`, `alarm_state`, `alarm_person_ids`, `warning_person_ids`.

## Kiểm thử và giới hạn

- `python -m pytest -q`: kiểm thử logic và API trong môi trường phát triển.
- Chưa xác nhận độ chính xác của các hệ số 1,15 và 1,12 trên vị trí camera thực tế; cần hiệu chỉnh theo mặt bằng và góc nhìn.
- Phép mở rộng đa giác quanh trọng tâm có thể bị cắt tại biên ảnh do tọa độ được giới hạn 0–1.
- Vùng WARNING dùng nhận diện theo frame hiện tại; vùng ALARM dùng hysteresis theo Track ID.
- Kiểm thử tự động không thay thế kiểm thử webcam USB, ánh sáng ban ngày/ban đêm và phần cứng thật.
