# Mô hình nhà kho (bản chỉnh lại)

## Ngoài kho
- Khu đất trước cửa. Dán băng dính hình chữ nhật = **vùng A**.
- Camera ngoài gắn cao nhìn từ trên xuống, thấy trọn vùng A và cửa.

## Trong kho
- Vạch băng dính vàng hình **chữ +** chia sàn thành 4 góc đánh số 1 đến 4.
- Mỗi góc một màu băng dính viền riêng (không trùng màu người):
  1 Nhập = xám, 2 Xuất = trắng, 3 Quan trọng = đen, 4 Cực kỳ quan trọng = xanh lá.
- Camera trong gắn trên cao, ở giữa, thấy cả 4 góc.

## Cửa
- Đầu đọc RC522 cạnh cửa. Vòng chữ + bắt đầu từ cửa.
- Chỗ để mạch: hộc nhỏ cạnh cửa (ESP32, RC522, còi/đèn).

## Người và hàng
- Mỗi người Lego một màu: đỏ, xanh dương, vàng, cam, tím (tối đa 5).
- Thùng hàng = khối Lego/hộp nhỏ **cùng một màu riêng** (nâu hoặc trắng).
- Không dùng màu xanh lá và xám/trắng/đen cho người (trùng băng dính).

## Vật liệu gợi ý
Thùng carton hoặc foam board, băng dính màu, 2 cây đỡ camera (ống/que), hộp nhựa nhỏ cho mạch.
Đo sẵn kích thước để camera thấy đủ khu vực rồi mới dán băng.

## Quy đổi thời gian
TIME_SCALE = 60 trong `server/main.py`: 1 giây demo = 60 giây thật (15 giây demo = 15 phút).
