"""Run a trained YOLO model on the notebook webcam."""

from __future__ import annotations

import argparse

import cv2
from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect litter in a webcam stream.")
    parser.add_argument("--weights", default="runs/trash-detector/weights/best.pt", help="Path to trained weights.")
    parser.add_argument("--camera", type=int, default=0, help="Webcam index.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    args = parser.parse_args()

    model = YOLO(args.weights)
    capture = cv2.VideoCapture(args.camera)

    if not capture.isOpened():
        raise RuntimeError(f"Could not open camera {args.camera}")

    try:
        while True:
            success, frame = capture.read()
            if not success:
                break

            result = model.predict(frame, imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
            annotated_frame = result.plot()

            cv2.imshow("ecobot-vision", annotated_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        capture.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
