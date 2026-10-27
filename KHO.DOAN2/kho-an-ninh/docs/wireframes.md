# Nháp giao diện (vẽ lại ra giấy)

## Trang xem camera (Camera ngoài)
```
+------------------------------------------------+
| Tổng quan | [Camera ngoài] | Camera trong | ... |
+------------------------------------------------+
| +--------------------------------------------+ |
| |            hình camera từ trên xuống       | |
| |        +--------------+                    | |
| |        | Vùng A       |  (khung vàng)      | |
| |        +--------------+                    | |
| +--------------------------------------------+ |
| [Người trong vùng: 2] [Đã quẹt: 1] [Lâu nhất: 15 giây ≈ 15 phút] |
+------------------------------------------------+
```

## Camera trong (sơ đồ kho dấu +)
```
+-----------+-----------+
| 1 Nhập    | 2 Xuất    |   vùng có người: sáng vàng
|           |           |   người đứng sai vùng: đỏ
+===========+===========+   (băng vàng = lối đi chữ +)
| 3 Quan    | 4 Cực kỳ |
|   trọng   |   quan trọng |
+-----------[Cửa]--------+
```

## Trang lịch sử
```
| Giờ | UID | Tên | Kết quả | Lý do |
| 09:01 | AA11.. | Minh | Cho phép |  |
| 09:05 | 9F3C.. | Không rõ | Từ chối | Thẻ lạ |
```

## Trang cấp thẻ
```
UID [__________] [UID quẹt gần nhất]
Tên [______]  Tuổi [__]  Hạn dùng [date]  Lượt/ngày [3]
Vùng: [ ] Nhập [ ] Xuất [ ] Quan trọng [ ] Cực kỳ quan trọng
Loại hàng [____]  Số thùng [__]  Màu [v dropdown]
[Cấp thẻ]
```
