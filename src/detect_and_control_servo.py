"""Detect litter from ESP32-CAM frames and trigger a servo controller."""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from typing import Protocol

import cv2
import requests
from ultralytics import YOLO

from detect_camera import build_reader


class ServoController(Protocol):
    def trigger(self, command: str, angle: int) -> None:
        ...

    def close(self) -> None:
        ...


class DryRunServoController:
    def trigger(self, command: str, angle: int) -> None:
        logging.info("Dry run servo command: %s angle=%s", command, angle)

    def close(self) -> None:
        return


class SerialServoController:
    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        import serial

        self._serial = serial.Serial(port, baudrate=baudrate, timeout=timeout)
        time.sleep(2.0)
        self._serial.reset_input_buffer()

    def trigger(self, command: str, angle: int) -> None:
        message = command if command else str(angle)
        self._serial.write(f"{message}\n".encode("ascii"))
        self._serial.flush()

        response = self._serial.readline().decode("ascii", errors="ignore").strip()
        if response:
            logging.info("Servo serial response: %s", response)

    def close(self) -> None:
        self._serial.close()


class HttpServoController:
    def __init__(self, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def trigger(self, command: str, angle: int) -> None:
        if command in {"LEFT", "CENTER", "RIGHT", "PICK", "OPEN"}:
            endpoint = command.lower()
            url = f"{self.base_url}/{endpoint}"
            response = requests.get(url, timeout=self.timeout)
        else:
            response = requests.get(
                f"{self.base_url}/servo",
                params={"angle": angle},
                timeout=self.timeout,
            )
        response.raise_for_status()
        logging.info("Servo HTTP response: %s", response.text.strip())

    def close(self) -> None:
        return


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


def find_best_detection(result, frame_width: int, trash_classes: set[str]) -> Detection | None:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return None

    names = result.names
    best: Detection | None = None

    for box in boxes:
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        class_name = str(names.get(class_id, class_id))

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


def build_servo_controller(args: argparse.Namespace) -> ServoController:
    if args.servo_mode == "none":
        return DryRunServoController()
    if args.servo_mode == "serial":
        if not args.serial_port:
            raise ValueError("--serial-port is required when --servo-mode serial")
        return SerialServoController(args.serial_port, args.baudrate, args.servo_timeout)
    if args.servo_mode == "http":
        if not args.servo_url:
            raise ValueError("--servo-url is required when --servo-mode http")
        return HttpServoController(args.servo_url, args.servo_timeout)
    raise ValueError(f"Unknown servo mode: {args.servo_mode}")


def command_for_detection(detection: Detection, use_direction: bool) -> str:
    return detection.direction if use_direction else "PICK"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Detect litter from an ESP32-CAM stream and trigger a servo."
    )
    parser.add_argument("--source", default="http://172.16.100.182:81/stream", help="ESP32-CAM stream URL.")
    parser.add_argument("--weights", default="yolov8n.pt", help="YOLO weights path.")
    parser.add_argument("--imgsz", type=int, default=320, help="YOLO inference image size.")
    parser.add_argument("--conf", type=float, default=0.60, help="Minimum detection confidence.")
    parser.add_argument("--device", default=None, help="Device identifier, for example cpu or cuda:0.")
    parser.add_argument("--framesize", default="qvga", help="ESP32-CAM frame size preset.")
    parser.add_argument("--timeout", type=float, default=5.0, help="ESP32-CAM HTTP timeout.")
    parser.add_argument("--reconnect-delay", type=float, default=1.0, help="ESP32-CAM reconnect delay.")
    parser.add_argument("--esp32", action="store_true", help="Force the ESP32-CAM MJPEG reader.")
    parser.add_argument("--cooldown", type=float, default=3.0, help="Seconds between servo triggers.")
    parser.add_argument("--servo-angle", type=int, default=90, help="Servo angle for PICK command.")
    parser.add_argument("--servo-mode", choices=("none", "serial", "http"), default="serial")
    parser.add_argument("--serial-port", help="Serial port, for example /dev/ttyUSB0 or COM3.")
    parser.add_argument("--baudrate", type=int, default=115200, help="Serial baudrate.")
    parser.add_argument("--servo-url", help="HTTP servo controller URL, for example http://192.168.0.80.")
    parser.add_argument("--servo-timeout", type=float, default=2.0, help="Servo command timeout.")
    parser.add_argument(
        "--trash-classes",
        default="",
        help="Comma-separated class names to accept. Empty means any detected class is accepted.",
    )
    parser.add_argument(
        "--send-direction",
        action="store_true",
        help="Send LEFT/CENTER/RIGHT based on object position instead of PICK.",
    )
    parser.add_argument("--no-display", action="store_true", help="Run without an OpenCV window.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    trash_classes = parse_classes(args.trash_classes)
    model = YOLO(args.weights)
    reader = build_reader(args)
    servo = build_servo_controller(args)
    last_trigger_at = 0.0

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
            detection = find_best_detection(result, frame.shape[1], trash_classes)

            now = time.monotonic()
            if detection and now - last_trigger_at >= args.cooldown:
                command = command_for_detection(detection, args.send_direction)
                servo.trigger(command, args.servo_angle)
                last_trigger_at = now
                logging.info(
                    "Detected %s with %.2f confidence, command=%s",
                    detection.class_name,
                    detection.confidence,
                    command,
                )

            if not args.no_display:
                annotated_frame = result.plot()
                if detection:
                    cv2.putText(
                        annotated_frame,
                        f"{detection.class_name} {detection.confidence:.2f} {detection.direction}",
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
        servo.close()
        reader.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
