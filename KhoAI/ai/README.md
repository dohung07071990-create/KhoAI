# Camera AI for KhoAI

- YOLOv8 detects COCO class `person` (class 0).
- ByteTrack assigns persistent track IDs across frames; these IDs are tracking identifiers, not biometric identity.
- Intrusion events are generated when a tracked person enters the configured polygon. Recent events are available at `/api/camera/events`.
- The zone is loaded from `ai/zone.json` (normalized x/y values in `[0, 1]`); the built-in default is used if the file does not exist.
- Stop the FastAPI server before running `python ai/draw_zone.py`, because only one process should own the USB camera. Left-click points, `S` save, `C` clear, `Q` quit.
- Set `CAMERA_INDEX=1` if your USB camera is camera index 1. Default is 0.
- Set `KHOAI_YOLO_MODEL` to use custom weights; otherwise `yolov8n.pt` is used. Set `KHOAI_AI_DEVICE` to `cpu` or a supported device.

Install AI dependencies from the project root with `python -m pip install -r ai/requirements.txt`. The first model load may download `yolov8n.pt`.
