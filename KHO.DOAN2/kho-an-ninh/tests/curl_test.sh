#!/bin/bash
# Giả lập ESP32 + camera, chưa cần mạch. Chạy server trước: cd server && uvicorn main:app --port 8000
S=http://localhost:8000; H='Content-Type: application/json'
echo "1) Thẻ lạ (kỳ vọng deny/unknown_card)";  curl -s -X POST $S/api/rfid/scan -H "$H" -d '{"uid":"AA11BB22"}'; echo
echo "2) UID quẹt gần nhất";                    curl -s $S/api/rfid/last-unknown; echo
echo "3) Cấp thẻ cho UID đó (hạn dùng, 2 lượt/ngày, vùng Nhập+Xuất, áo đỏ)"
curl -s -X POST $S/api/cards -H "$H" -d '{"uid":"AA11BB22","name":"Minh","age":12,"expires_at":"2099-12-31","daily_quota":2,"zones":["entry","exit"],"color":"red","item":"Hộp A","boxes":2}'; echo
echo "4) Quẹt lần 1, 2 (allow), lần 3 (quota_exhausted)"
for i in 1 2 3; do curl -s -X POST $S/api/rfid/scan -H "$H" -d '{"uid":"AA11BB22"}'; echo; done
echo "5) Thẻ hết hạn"
curl -s -X POST $S/api/cards -H "$H" -d '{"uid":"CC33DD44","name":"Cũ","expires_at":"2020-01-01"}'; echo
curl -s -X POST $S/api/rfid/scan -H "$H" -d '{"uid":"CC33DD44"}'; echo
echo "6) Heartbeat";                            curl -s -X POST $S/api/device/heartbeat -H "$H" -d '{"device_id":"esp32-door"}'; echo
echo "7) Camera ngoài: 3 người, đứng 15 giây demo (= 15 phút thật) -> tailgating + loitering"
curl -s -X POST $S/api/events -H "$H" -d '{"camera":"outside","people_in_zone":3,"max_seconds":15}'; echo
echo "8) Camera trong: người áo đỏ đứng vùng Quan trọng (không được phép) -> wrong_zone severe"
curl -s -X POST $S/api/events -H "$H" -d '{"camera":"inside","people":[{"color":"red","zone":"important","seconds":2}],"boxes":5}'; echo
echo "9) Cảnh báo / lịch sử";  curl -s $S/api/alerts; echo; curl -s $S/api/scans; echo
echo "10) Xử lý cảnh báo số 1"; curl -s -X POST $S/api/alerts/1/ack; echo
