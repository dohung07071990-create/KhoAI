"""Nhận diện người Lego theo màu (OpenCV HSV) rồi gửi lên POST /api/events.
pip install opencv-python requests numpy
Chạy từ thư mục gốc KhoAI: python tools/color_detect.py --camera 0 --mode inside
Mặc định gửi sự kiện đến KhoAI tại http://127.0.0.1:3000; đặt KHOAI_SERVER_URL nếu dùng cổng khác.
Trước khi demo: chạy với --calib để xem mặt nạ từng màu và chỉnh HSV bên dưới."""
import argparse, os, time, cv2, numpy as np, requests

SERVER = os.getenv("KHOAI_SERVER_URL", "http://127.0.0.1:3000")
MIN_AREA = 400   # điểm ảnh tối thiểu của một khối màu
# (H thấp, S thấp, V thấp) - (H cao, S cao, V cao). Chỉnh lại theo đèn thật.
COLORS = {"red": ((0,120,80),(8,255,255)), "orange": ((9,120,80),(20,255,255)),
          "yellow": ((21,100,100),(34,255,255)), "blue": ((100,120,60),(130,255,255)),
          "purple": ((131,60,60),(160,255,255))}
BOX_COLOR = ((10,60,60),(25,200,200))   # màu thùng hàng (nâu) - chỉnh lại
# Vùng ROI (x1,y1,x2,y2) theo điểm ảnh khung 640x480: VẼ MỘT LẦN vì camera cố định
OUTSIDE_A = (160, 200, 480, 440)
INSIDE = {"entry": (0,0,320,240), "exit": (320,0,640,240),
          "important": (0,240,320,480), "critical": (320,240,640,480)}

def blobs(hsv, lo, hi):
    mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5,5), np.uint8))
    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        if cv2.contourArea(c) >= MIN_AREA:
            x, y, w, h = cv2.boundingRect(c); out.append((x + w//2, y + h//2))
    return out

def zone_of(pt, zones):
    for name, (x1,y1,x2,y2) in zones.items():
        if x1 <= pt[0] < x2 and y1 <= pt[1] < y2: return name

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--camera", default="0")
    ap.add_argument("--mode", default="inside"); ap.add_argument("--calib", action="store_true")
    a = ap.parse_args()
    cap = cv2.VideoCapture(int(a.camera) if a.camera.isdigit() else a.camera)
    since, last_post = {}, 0       # (màu,vùng) -> lúc bắt đầu thấy
    while True:
        ok, frame = cap.read()
        if not ok: break
        frame = cv2.resize(frame, (640, 480)); hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        people, t = [], time.time()
        for color, (lo, hi) in COLORS.items():
            for pt in blobs(hsv, lo, hi):
                z = "A" if a.mode == "outside" and zone_of(pt, {"A": OUTSIDE_A}) else \
                    zone_of(pt, INSIDE) if a.mode == "inside" else None
                if z:
                    since.setdefault((color, z), t)
                    people.append({"color": color, "zone": z, "seconds": round(t - since[(color, z)], 1)})
                    cv2.circle(frame, pt, 8, (0,255,0), 2); cv2.putText(frame, color, pt, 0, .5, (255,255,255), 1)
        active = {(p["color"], p["zone"]) for p in people}
        for k in [k for k in since if k not in active]: since.pop(k)
        if t - last_post > 1:
            body = ({"camera": "outside", "people_in_zone": len(people),
                     "max_seconds": max([p["seconds"] for p in people], default=0)} if a.mode == "outside" else
                    {"camera": "inside", "people": people, "boxes": len(blobs(hsv, *BOX_COLOR))})
            try: requests.post(SERVER + "/api/events", json=body, timeout=2)
            except requests.RequestException as e: print("Không gửi được:", e)
            last_post = t
        cv2.imshow("color_detect (q để thoát)", frame)
        if cv2.waitKey(1) == ord("q"): break

if __name__ == "__main__": main()
