"""Detect litter from ESP32-CAM frames and trigger the ESP32-CAM servo route."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass

import cv2
import requests
from ultralytics import YOLO

from detect_camera import build_reader


ESP32_IP = "192.168.0.87"
SERVO_URL = f"http://{ESP32_IP}/servo"

CONFIDENCE_THRESHOLD = 0.60
COOLDOWN_SECONDS = 3
SERVO_TIMEOUT_SECONDS = 3

ESP32_STREAM_URL = f"http://{ESP32_IP}:81/stream"
CLASSES_LIXO_COCO = {"bottle", "cup", "bowl", "can", "plastic bag", "cardboard"}
CLASSES_MARCADORAS_COCO = {"person", "car", "dog", "bottle", "cup", "bowl"}

ultimo_acionamento = 0.0


@dataclass(frozen=True)
class Detection:
    class_name: str
    confidence: float
    center_x: float
    frame_width: int

    @property
    def direction(self) -> str:
        left_limit = self.frame_width / 3
        right_limit = 2 * self.frame_width / 3
        if self.center_x < left_limit:
            return "LEFT"
        if self.center_x > right_limit:
            return "RIGHT"
        return "CENTER"


def parse_classes(value: str) -> set[str]:
    return {item.strip().lower() for item in value.split(",") if item.strip()}


def get_class_name(names, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)


def acionar_servo() -> bool:
    global ultimo_acionamento

    agora = time.time()

    if agora - ultimo_acionamento < COOLDOWN_SECONDS:
        return False

    try:
        resposta = requests.get(SERVO_URL, timeout=SERVO_TIMEOUT_SECONDS)
        print(f"Servo acionado: {resposta.text}")
        ultimo_acionamento = agora
        return True
    except requests.RequestException as erro:
        print(f"Erro ao acionar servo: {erro}")
        return False


def using_coco_model(model: YOLO) -> bool:
    names = model.names.values() if isinstance(model.names, dict) else model.names
    model_classes = {str(name).lower() for name in names}
    return len(model_classes) >= 70 and CLASSES_MARCADORAS_COCO.issubset(model_classes)


def resolve_trash_classes(args: argparse.Namespace, model: YOLO) -> set[str]:
    if args.trash_classes:
        return parse_classes(args.trash_classes)
    if using_coco_model(model):
        return CLASSES_LIXO_COCO
    return set()


def find_best_detection(
    result,
    frame_width: int,
    trash_classes: set[str],
    confidence_threshold: float,
) -> Detection | None:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None

    names = result.names
    best: Detection | None = None

    for box in boxes:
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        class_name = get_class_name(names, class_id)

        if confidence < confidence_threshold:
            continue
        if trash_classes and class_name.lower() not in trash_classes:
            continue

        xyxy = box.xyxy[0].tolist()
        center_x = (xyxy[0] + xyxy[2]) / 2
        detection = Detection(
            class_name=class_name,
            confidence=confidence,
            center_x=center_x,
            frame_width=frame_width,
        )

        if best is None or detection.confidence > best.confidence:
            best = detection

    return best


def main() -> None:
    global COOLDOWN_SECONDS, SERVO_TIMEOUT_SECONDS, SERVO_URL

    parser = argparse.ArgumentParser(
        description="Detect litter from an ESP32-CAM stream and trigger a servo."
    )
    parser.add_argument("--source", default=ESP32_STREAM_URL, help="ESP32-CAM stream URL.")
    parser.add_argument("--weights", default="yolov8n.pt", help="YOLO weights path.")
    parser.add_argument("--imgsz", type=int, default=320, help="YOLO inference image size.")
    parser.add_argument("--conf", type=float, default=CONFIDENCE_THRESHOLD, help="Minimum detection confidence.")
    parser.add_argument("--device", default=None, help="Device identifier, for example cpu or cuda:0.")
    parser.add_argument("--framesize", default="qvga", help="ESP32-CAM frame size preset.")
    parser.add_argument("--timeout", type=float, default=5.0, help="ESP32-CAM HTTP timeout.")
    parser.add_argument("--reconnect-delay", type=float, default=1.0, help="ESP32-CAM reconnect delay.")
    parser.add_argument("--esp32", action="store_true", help="Force the ESP32-CAM MJPEG reader.")
    parser.add_argument("--cooldown", type=float, default=COOLDOWN_SECONDS, help="Seconds between servo triggers.")
    parser.add_argument("--servo-url", default=SERVO_URL, help="ESP32-CAM servo URL, for example http://192.168.0.80/servo.")
    parser.add_argument("--servo-timeout", type=float, default=SERVO_TIMEOUT_SECONDS, help="Servo HTTP timeout.")
    parser.add_argument(
        "--trash-classes",
        default="",
        help=(
            "Comma-separated class names to accept. Empty uses COCO trash classes "
            "for COCO models and any class for custom trash models."
        ),
    )
    parser.add_argument("--no-display", action="store_true", help="Run without an OpenCV window.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    COOLDOWN_SECONDS = args.cooldown
    SERVO_TIMEOUT_SECONDS = args.servo_timeout
    SERVO_URL = args.servo_url

    model = YOLO(args.weights)
    trash_classes = resolve_trash_classes(args, model)
    reader = build_reader(args)

    try:
        while True:
            success, frame = reader.read()
            if not success or frame is None:
                time.sleep(0.01)
                continue

            result = model.predict(
                frame,
                imgsz=args.imgsz,
                conf=args.conf,
                device=args.device,
                verbose=False,
            )[0]
            detection = find_best_detection(result, frame.shape[1], trash_classes, args.conf)

            if detection:
                acionar_servo()
                logging.info(
                    "Detected trash class %s with %.2f confidence",
                    detection.class_name,
                    detection.confidence,
                )

            if not args.no_display:
                annotated_frame = result.plot()
                if detection:
                    cv2.putText(
                        annotated_frame,
                        f"{detection.class_name} {detection.confidence:.2f}",
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (0, 255, 0),
                        2,
                    )
                cv2.imshow("ecobot-vision servo", annotated_frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
    finally:
        reader.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
