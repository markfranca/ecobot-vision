"""Detect litter from ESP32-CAM frames and trigger a servo over serial."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from typing import Optional

import cv2
from ultralytics import YOLO

try:
    import serial
except ImportError:  # pragma: no cover - depends on local environment
    serial = None

from detect_camera import build_reader


SERIAL_PORT = "COM5"  # vou alterar conforme minha porta
BAUDRATE = 115200
SERVO_COOLDOWN = 5

CONFIDENCE_THRESHOLD = 0.60
COOLDOWN_SECONDS = SERVO_COOLDOWN

ESP32_STREAM_URL = "http://192.168.0.87:81/stream"
TRASH_CLASSES = {"bottle", "cup", "can", "plastic bag", "paper", "cardboard", "trash", "garbage"}
COCO_TRASH_CLASSES = {"bottle", "cup", "bowl"}
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


def acionar_servo_serial(serial_bridge: serial.Serial) -> bool:
    global ultimo_acionamento

    agora = time.monotonic()

    if agora - ultimo_acionamento < COOLDOWN_SECONDS:
        return False

    try:
        serial_bridge.write(b"SERVO\n")
        serial_bridge.flush()
        logging.info("Comando SERVO enviado pela serial")
        ultimo_acionamento = agora
        return True
    except serial.SerialException as erro:
        logging.error("Erro ao enviar comando SERVO pela serial: %s", erro)
        return False


def acionar_servo_none() -> bool:
    logging.info("Servo desativado por --servo-mode none")
    return True


def using_coco_model(model: YOLO) -> bool:
    names = model.names.values() if isinstance(model.names, dict) else model.names
    model_classes = {str(name).lower() for name in names}
    return len(model_classes) >= 70 and CLASSES_MARCADORAS_COCO.issubset(model_classes)


def resolve_trash_classes(args: argparse.Namespace, model: YOLO) -> set[str]:
    if args.trash_classes is not None:
        return parse_classes(args.trash_classes)
    if using_coco_model(model):
        return COCO_TRASH_CLASSES
    return TRASH_CLASSES


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
    global COOLDOWN_SECONDS

    parser = argparse.ArgumentParser(
        description="Detect litter from an ESP32-CAM stream and trigger a servo over serial."
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
    parser.add_argument(
        "--servo-mode",
        default="serial",
        choices=("serial", "none"),
        help="Servo control mode. Use serial to send commands over USB or none to disable servo output.",
    )
    parser.add_argument("--serial-port", default=SERIAL_PORT, help="Serial port connected to the ESP32-CAM bridge.")
    parser.add_argument("--baudrate", type=int, default=BAUDRATE, help="Serial baud rate.")
    parser.add_argument(
        "--trash-classes",
        default=None,
        help=(
            "Comma-separated class names considered trash. If omitted, the script uses "
            "COCO-compatible classes for COCO models and TRASH_CLASSES for custom models."
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

    serial_bridge: Optional[serial.Serial] = None
    if args.servo_mode == "serial":
        if serial is None:
            logging.error("pyserial is not installed; install requirements to use --servo-mode serial")
            return
        try:
            serial_bridge = serial.Serial(args.serial_port, args.baudrate, timeout=1)
            logging.info("Serial port opened on %s at %d baud", args.serial_port, args.baudrate)
            time.sleep(2)
            logging.info("Serial bridge ready after reset wait")
        except serial.SerialException as erro:
            logging.error("Erro ao abrir porta serial %s: %s", args.serial_port, erro)
            return

    def trigger_servo() -> bool:
        if args.servo_mode == "none":
            return acionar_servo_none()
        if serial_bridge is None:
            return False
        return acionar_servo_serial(serial_bridge)

    reader = None

    try:
        model = YOLO(args.weights)
        trash_classes = resolve_trash_classes(args, model)
        logging.info("Using trash classes: %s", ", ".join(sorted(trash_classes)))
        reader = build_reader(args)

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
                trigger_servo()
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
        if reader is not None:
            reader.release()
        if serial_bridge is not None:
            serial_bridge.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
