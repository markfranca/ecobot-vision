"""Run a trained YOLO model on a camera index or stream URL."""

from __future__ import annotations

import argparse

import cv2
from ultralytics import YOLO


def parse_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect litter from a camera source or stream.")
    parser.add_argument("--weights", default="runs/detect/train/weights/best.pt", help="Path to trained weights.")
    parser.add_argument("--source", default="0", help="Camera index or stream URL.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    args = parser.parse_args()

    model = YOLO(args.weights)
    capture = cv2.VideoCapture(parse_source(args.source))

    if not capture.isOpened():
        raise RuntimeError(f"Could not open source {args.source}")

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