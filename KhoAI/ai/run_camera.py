"""Display the annotated camera feed; press q in the window to quit."""

import logging
import time

import cv2
import numpy as np

from person_detector import detector


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        while True:
            jpeg = detector.read_jpeg()
            if jpeg is None:
                # Keep the loop responsive while the camera is unavailable.
                if cv2.waitKey(100) & 0xFF == ord("q"):
                    break
                continue

            frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            if frame is None:
                time.sleep(0.05)
                continue
            cv2.imshow("Person detection - press q to quit", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    except KeyboardInterrupt:
        pass
    finally:
        detector.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
