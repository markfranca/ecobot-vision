"""Train a YOLO model for litter detection."""

from __future__ import annotations

import argparse

from ultralytics import YOLO


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a YOLO model.")
    parser.add_argument("--data", default="dataset/data.yaml", help="Path to the YOLO data.yaml file.")
    parser.add_argument("--model", default="yolov8n.pt", help="Base YOLO weights to start from.")
    parser.add_argument("--epochs", type=int, default=50, help="Number of training epochs.")
    parser.add_argument("--imgsz", type=int, default=640, help="Training image size.")
    parser.add_argument("--batch", type=int, default=16, help="Batch size.")
    parser.add_argument("--project", default="runs", help="YOLO project directory.")
    parser.add_argument("--name", default="trash-detector", help="Run name.")
    parser.add_argument("--device", default=None, help="Device identifier, for example 0 or cpu.")
    args = parser.parse_args()

    model = YOLO(args.model)
    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.name,
        device=args.device,
    )


if __name__ == "__main__":
    main()