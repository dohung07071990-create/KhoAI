# KhoAI dev.24 – Telegram Integration

## Thiết kế
- Telegram là adapter tùy chọn, mặc định tắt (`TELEGRAM_ENABLED=0`).
- Polling qua HTTPS; không cần mở cổng webhook.
- Chỉ chấp nhận private chat có ID nằm trong `TELEGRAM_ALLOWED_CHAT_IDS`.
- Bot không import AI/Decision Engine để điều khiển; chỉ đọc trạng thái/sự kiện và gọi callback nghiệp vụ backend.
- ACK từ Telegram ghi `TELEGRAM_ADMIN_ACTION` vào `system_access_logs`.
- Telegram lỗi hoặc mất mạng không được phép làm dừng camera, AI Worker hay API.

## Cấu hình
1. Tạo bot bằng BotFather và lấy token mới.
2. Đặt trong `.env`:
   ```env
   TELEGRAM_ENABLED=1
   TELEGRAM_BOT_TOKEN=YOUR_NEW_TOKEN
   TELEGRAM_ALLOWED_CHAT_IDS=YOUR_PRIVATE_CHAT_ID
   TELEGRAM_POLL_TIMEOUT=25
   TELEGRAM_NOTIFY_INTERVAL=3
   ```
3. Khởi động lại backend. Gửi `/start`, `/status`, `/alerts`.
4. Không commit `.env`; chỉ commit `.env.example`.

## Lệnh
`/help`, `/id`, `/status`, `/alerts`, `/ack <id>`, `/ackall`, `/snapshot`.

## Bảo mật và phạm vi
- `/id` là lệnh duy nhất phản hồi người chưa được allowlist, chỉ trong private chat.
- Các lệnh khác yêu cầu chat ID và sender ID cùng khớp allowlist.
- ACK ghi audit log nhưng không tạo admin web session. Telegram allowlist là quyền vận hành độc lập; chỉ thêm ID của người có quyền quản trị.
- Không tích hợp CallMeBot, gọi điện hay gTTS ở dev.24; các chức năng bên thứ ba trong bot cũ không được mang sang.
- Outbox SQLite lưu trạng thái riêng theo `(chat_id,event_id)`. Cursor chỉ dùng discovery, không dùng làm bằng chứng gửi thành công. Mô hình là at-least-once: nếu tiến trình dừng sau khi Telegram nhận tin nhưng trước khi SQLite commit, một tin trùng có thể xuất hiện khi khởi động lại; Telegram Bot API không cung cấp idempotency key cho thao tác gửi tin. Migration dev.24.2 replay mặc định 6 giờ; điều chỉnh `TELEGRAM_REPLAY_HOURS`.
- Text được gửi trước và có nút ACK. Ảnh được gửi riêng dưới dạng reply sau khi evidence `available`; TTL mặc định 30 phút (`TELEGRAM_EVIDENCE_TTL_SECONDS`).
- Retry mạng/5xx có backoff tối đa 15 phút; 429 tôn trọng `retry_after`; 403 retry theo chat; 401/404 mở circuit breaker, probe `getMe` mỗi 60 giây. WARNING tồn đọng số lượng lớn có thể được tổng hợp sau 2 giờ; SEVERE không bị tổng hợp.
- Một SQLite lease ngăn nhiều instance cùng polling/gửi. Admin có thể xem `/api/admin/telegram/status` và retry qua `POST /api/admin/telegram/retry/{chat_id}/{event_id}`.
- `TELEGRAM_INCLUDE_PERSON_NAME=0` ẩn tên đã biết từ bảng thẻ; ảnh có thể vẫn chứa khuôn mặt và không được xem là ẩn danh hoàn toàn.
- Chưa xác minh gửi/nhận thật với Telegram, token thật, ảnh evidence thật hoặc vận hành đa tiến trình trên máy triển khai.
