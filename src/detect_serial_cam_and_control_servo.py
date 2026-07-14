"""Detect litter from ESP32-CAM serial JPEG frames and trigger a servo by serial."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import time

import cv2
import serial
from ultralytics import YOLO

from serial_camera_reader import SerialCameraReader


DEFAULT_CAMERA_BAUDRATE = 921600
DEFAULT_SERVO_BAUDRATE = 115200
DEFAULT_CONFIDENCE = 0.60
DEFAULT_COOLDOWN = 5.0
DEFAULT_TRASH_CLASSES = ("bottle", "cup", "bowl")


def get_class_name(names, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if 0 <= class_id < len(names):
        return str(names[class_id])
    return str(class_id)


def draw_detection(frame, box, class_name: str, confidence: float) -> None:
    x1, y1, x2, y2 = [int(value) for value in box.xyxy[0].tolist()]
    label = f"{class_name} {confidence:.2f}"

    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        frame,
        label,
        (x1, max(y1 - 8, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2,
    )


def detect_objects(
    result,
    frame,
    trash_classes: set[str],
    confidence_threshold: float,
    trigger_any: bool,
) -> tuple[bool, list[str]]:
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return False, []

    should_trigger = False
    detections = []

    for box in boxes:
        confidence = float(box.conf[0])
        class_id = int(box.cls[0])
        class_name = get_class_name(result.names, class_id).lower()

        if confidence < confidence_threshold:
            continue

        detections.append(f"{class_name} {confidence:.2f}")
        if not trigger_any and class_name not in trash_classes:
            continue

        draw_detection(frame, box, class_name, confidence)
        should_trigger = True

    return should_trigger, detections


def trigger_servo(servo_serial: serial.Serial, last_trigger: float, cooldown: float) -> float:
    now = time.monotonic()
    if now - last_trigger < cooldown:
        return last_trigger

    try:
        servo_serial.write(b"SERVO\n")
        servo_serial.flush()
        logging.info("Comando SERVO enviado para a ESP32 DevKit")
        return now
    except serial.SerialException as exc:
        logging.error("Erro ao enviar SERVO pela serial: %s", exc)
        return last_trigger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run YOLO on ESP32-CAM JPEG frames received by serial and trigger a servo by serial."
    )
    parser.add_argument("--camera-port", required=True, help="Serial port where ESP32-CAM sends JPEG frames.")
    parser.add_argument("--camera-baudrate", type=int, default=DEFAULT_CAMERA_BAUDRATE)
    parser.add_argument("--servo-port", required=True, help="Serial port connected to the ESP32 DevKit servo controller.")
    parser.add_argument("--servo-baudrate", type=int, default=DEFAULT_SERVO_BAUDRATE)
    parser.add_argument("--weights", default="yolov8n.pt", help="YOLO weights path.")
    parser.add_argument("--imgsz", type=int, default=320, help="YOLO inference image size.")
    parser.add_argument("--conf", type=float, default=DEFAULT_CONFIDENCE, help="Minimum detection confidence.")
    parser.add_argument("--device", default=None, help="Device identifier, for example cpu or cuda:0.")
    parser.add_argument("--cooldown", type=float, default=DEFAULT_COOLDOWN, help="Seconds between servo triggers.")
    parser.add_argument("--trash-classes", nargs="+", default=list(DEFAULT_TRASH_CLASSES))
    parser.add_argument("--trigger-any", action="store_true", help="Trigger the servo for any detected YOLO class.")
    parser.add_argument("--camera-timeout", type=float, default=5.0, help="Camera serial read timeout.")
    parser.add_argument("--camera-reset-wait", type=float, default=2.0, help="Seconds to wait after opening camera serial.")
    parser.add_argument("--sync-timeout", type=float, default=2.0, help="Seconds to search for a valid frame marker per read.")
    parser.add_argument("--servo-timeout", type=float, default=2.0, help="Servo serial timeout.")
    parser.add_argument("--max-frame-size", type=int, default=200_000, help="Maximum JPEG frame size in bytes.")
    parser.add_argument("--status-every", type=float, default=2.0, help="Seconds between camera status logs.")
    parser.add_argument("--save-debug-frame", help="Path to periodically save the latest annotated frame.")
    parser.add_argument("--no-display", action="store_true", help="Run without an OpenCV window.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    camera = None
    servo_serial = None

    try:
        camera = SerialCameraReader(
            args.camera_port,
            args.camera_baudrate,
            timeout=args.camera_timeout,
            max_frame_size=args.max_frame_size,
            sync_timeout=args.sync_timeout,
        )
        logging.info("Serial da ESP32-CAM aberta em %s a %d baud", args.camera_port, args.camera_baudrate)
        time.sleep(args.camera_reset_wait)
        camera.reset_input_buffer()
        logging.info("ESP32-CAM pronta apos espera de reset da serial")

        servo_serial = serial.Serial(args.servo_port, args.servo_baudrate, timeout=args.servo_timeout)
        logging.info("Serial da ESP32 DevKit aberta em %s a %d baud", args.servo_port, args.servo_baudrate)
        time.sleep(2)
        logging.info("ESP32 DevKit pronta apos espera de reset da serial")

        model = YOLO(args.weights)
        trash_classes = {class_name.lower() for class_name in args.trash_classes}
        if args.trigger_any:
            logging.info("Modo de acionamento: qualquer objeto detectado acima de %.2f", args.conf)
        else:
            logging.info("Classes consideradas lixo: %s", ", ".join(sorted(trash_classes)))

        last_trigger = 0.0
        frame_count = 0
        last_status = time.monotonic()
        debug_frame_path = Path(args.save_debug_frame) if args.save_debug_frame else None

        while True:
            success, frame = camera.read()
            if not success or frame is None:
                now = time.monotonic()
                if now - last_status >= args.status_every:
                    logging.info(
                        (
                            "Aguardando frame valido da camera | bytes analisados: %d | "
                            "sync timeouts: %d | starts: %d | buffer: %d bytes | pacote parcial: %d bytes | "
                            "tamanhos invalidos: %d | END invalidos: %d | JPEG invalidos: %d"
                        ),
                        camera.bytes_scanned,
                        camera.sync_timeouts,
                        camera.start_markers_found,
                        camera.buffer_size,
                        camera.partial_frame_size,
                        camera.invalid_frame_sizes,
                        camera.invalid_end_markers,
                        camera.invalid_jpegs,
                    )
                    last_status = now
                continue

            frame_count += 1

            result = model.predict(
                frame,
                imgsz=args.imgsz,
                conf=args.conf,
                device=args.device,
                verbose=False,
            )[0]

            should_trigger, detections = detect_objects(
                result,
                frame,
                trash_classes,
                args.conf,
                args.trigger_any,
            )
            if should_trigger:
                last_trigger = trigger_servo(servo_serial, last_trigger, args.cooldown)

            now = time.monotonic()
            if now - last_status >= args.status_every:
                height, width = frame.shape[:2]
                detected_text = ", ".join(detections) if detections else "nenhum objeto acima da confianca"
                logging.info(
                    "Camera OK: %d frames | ultimo JPEG %d bytes | frame %dx%d | deteccoes: %s",
                    frame_count,
                    camera.last_frame_size,
                    width,
                    height,
                    detected_text,
                )
                last_status = now

            if debug_frame_path is not None:
                cv2.imwrite(str(debug_frame_path), frame)

            if not args.no_display:
                cv2.imshow("ecobot-vision serial", frame)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
    except serial.SerialException as exc:
        logging.error("Erro abrindo ou usando serial: %s", exc)
    finally:
        if camera is not None:
            camera.release()
        if servo_serial is not None and servo_serial.is_open:
            servo_serial.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
