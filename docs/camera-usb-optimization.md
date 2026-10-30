# Camera USB ngoài – cách sử dụng phần tối ưu

Phần này chỉ áp dụng cho webcam USB/camera ngoài do pipeline Python + YOLOv8 + ByteTrack của KhoAI quản lý. Không thay đổi firmware ESP32, RFID hoặc luồng ESP32-CAM.

## Các điểm đã bổ sung

- Giữ một camera worker đọc khung hình mới nhất; luồng MJPEG và trình duyệt không tự mở thêm webcam.
- Endpoint `/api/camera/status` báo FPS camera, FPS AI, độ trễ xử lý, tuổi khung hình, số người phát hiện và trạng thái model.
- Có thể vẽ vùng bảo vệ bằng cách bấm các điểm trên tab **Camera ngoài**, sau đó bấm **Lưu vùng**. Cần ít nhất 3 điểm; tọa độ được chuẩn hóa và lưu vào file `ai/zone.json` (hoặc đường dẫn `KHOAI_ZONE_FILE`). Không cần khởi động lại server.
- Endpoint `/api/camera/events` trả về sự kiện từ worker camera và đồng bộ sự kiện an ninh vào bảng cảnh báo KhoAI hiện có. Sự kiện vào/ra vùng bình thường vẫn hiển thị trong lịch sử camera nhưng không tự biến thành cảnh báo toàn hệ thống.
- Sự kiện mới có ảnh bằng chứng JPEG (frame đã vẽ vùng và bounding box) tại `data/camera_evidence/`; endpoint `/api/camera/evidence/{event_id}.jpg` phục vụ ảnh. Thư mục được giới hạn mặc định 500 ảnh gần nhất (`KHOAI_CAMERA_EVIDENCE_MAX_FILES`).
- Heatmap chuyển động tại `/api/camera/heatmap` thể hiện mật độ vị trí người gần đây; giá trị suy giảm theo thời gian, mặc định half-life 45 giây (`KHOAI_HEATMAP_HALF_LIFE`). Nút “Heatmap chuyển động” trên tab Camera ngoài chuyển đổi giữa video AI và heatmap.
- Nếu luồng video mất kết nối, giao diện sẽ thử kết nối lại với endpoint MJPEG mặc định.

## Kiểm tra API

- `GET /api/camera/status` – tình trạng camera/model và số đo hiệu năng.
- `GET /api/camera/stream` – luồng MJPEG có khung YOLO, ID tracking và vùng bảo vệ.
- `GET /api/camera/zone` – đọc vùng bảo vệ hiện tại.
- `PUT /api/camera/zone` – lưu vùng; JSON mẫu:

```json
{
  "points": [[0.1, 0.25], [0.9, 0.25], [0.9, 0.95], [0.1, 0.95]]
}
```

Tọa độ `x` và `y` nằm trong khoảng `0–1`, tính từ góc trên bên trái khung hình. Nên đặt các điểm theo thứ tự quanh ranh giới và tránh các cạnh tự cắt nhau.
- `GET /api/camera/events` – lịch sử sự kiện từ worker camera USB.
- `GET /api/camera/snapshot` – một ảnh JPEG chưa vẽ overlay để kiểm tra nguồn hình.
- `GET /api/camera/heatmap` – ảnh nhiệt vị trí người xuất hiện gần đây.
- `GET /api/camera/evidence/{event_id}.jpg` – ảnh bằng chứng cho sự kiện camera USB.

## Thông số hiệu năng

Các chỉ số FPS và độ trễ là số đo quan sát, không phải cam kết hiệu năng. Hãy thử camera trong điều kiện thực tế và thay đổi một tham số mỗi lần. Các biến môi trường sẵn có gồm `CAMERA_INDEX`, `KHOAI_FRAME_WIDTH`, `KHOAI_FRAME_HEIGHT`, `KHOAI_IMAGE_SIZE`, `KHOAI_CONFIDENCE`, `KHOAI_AI_DEVICE`, `KHOAI_ZONE_MODE`, `KHOAI_ENTER_FRAMES`, `KHOAI_EXIT_FRAMES` và `KHOAI_DWELL_SECONDS`.

Không chạy thêm một script khác mở cùng webcam trong lúc backend KhoAI đang dùng camera đó.

## Sự kiện camera USB

- `unauthorized_entry`: một track đã vào vùng bảo vệ nhưng chưa được liên kết thẻ hợp lệ; mức cao.
- `zone_entry`: track vào vùng; ghi lịch sử camera, không tự tạo cảnh báo toàn hệ thống nếu mức sự kiện là thấp.
- `zone_exit`: track rời vùng hoặc hết thời gian theo dõi; kèm thời lượng trong vùng nếu đo được.
- `long_dwell`: track ở trong vùng quá `KHOAI_DWELL_SECONDS`; chỉ phát một lần trong mỗi lượt ở trong vùng.

Track ID là định danh tạm thời do tracker cấp, không phải danh tính người. Heatmap chỉ phản ánh mật độ xuất hiện của detector, không phải bản đồ đo đạc chính xác.

## Ý tưởng tham khảo

Bản triển khai KhoAI này chỉ tham khảo ý tưởng kiến trúc/công năng từ các dự án công khai, không sao chép nguyên ứng dụng hoặc thay thế pipeline đang chạy:

- ZoneGuard: vòng đời vào/ra vùng, thời gian lưu lại và vị trí chân người để kiểm tra vùng bảo vệ — https://github.com/shivsegv/zoneguard
- PhantomEye: heatmap hoạt động và sự kiện theo dõi — https://github.com/Abu-Sameer-66/PhantomEye
- smart-campus-surveillance: phát hiện xâm nhập, tracking và ảnh bằng chứng — https://github.com/ChikkemNandaKishoreReddy/smart-campus-surveillance
- VirtualFenceMaker-OpenCV: ý tưởng thiết lập ranh giới vùng bảo vệ — https://github.com/emoy-kim/VirtualFenceMaker-OpenCV

KhoAI tiếp tục dùng YOLOv8n + ByteTrack hiện có. Không tích hợp Re-ID, nhận diện khuôn mặt hay suy luận cảm xúc trong bản vá này. Heatmap là chỉ báo mật độ phát hiện theo thời gian, không phải bằng chứng về ý định hoặc danh tính.
