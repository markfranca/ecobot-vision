"""Run a YOLO model on a camera index, generic stream, or ESP32-CAM MJPEG URL."""

from __future__ import annotations

import argparse
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlparse

import cv2
import numpy as np
import requests
from ultralytics import YOLO


ESP32_IP = "192.168.x.x"
SERVO_URL = f"http://{ESP32_IP}/servo"
SERVO_COOLDOWN_SECONDS = 4.0

TRASH_CLASSES = [
    "bottle",
    "cup",
    "plastic bag",
    "bag",
    "can",
    "paper",
    "cardboard",
    "carton",
    "trash",
    "garbage",
    "litter",
]

FRAME_SIZES = {
    "96x96": 0,
    "qqvga": 1,    # 160x120
    "128x128": 2,
    "qcif": 3,     # 176x144
    "hqvga": 4,    # 240x176
    "240x240": 5,
    "qvga": 6,     # 320x240
    "cif": 8,      # 400x296
    "hvga": 9,     # 480x320
    "vga": 10,     # 640x480
    "svga": 11,    # 800x600
    "xga": 12,     # 1024x768
    "hd": 13,      # 1280x720
    "sxga": 14,    # 1280x1024
    "uxga": 15,    # 1600x1200
}


@dataclass(frozen=True)
class Esp32StreamConfig:
    stream_url: str
    timeout_seconds: float = 5.0
    reconnect_delay_seconds: float = 1.0
    request_chunk_size: int = 4096
    max_jpeg_bytes: int = 2_000_000


class Esp32MjpegReader:
    """Low-latency MJPEG reader for ESP32-CAM CameraWebServer streams."""

    def __init__(self, config: Esp32StreamConfig) -> None:
        self.config = config
        self._frames: deque[np.ndarray] = deque(maxlen=1)
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._session = requests.Session()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._reader_loop, daemon=True)
        self._thread.start()

    def release(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._session.close()

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if not self._frames:
                return False, None
            return True, self._frames[-1].copy()

    def set_framesize(self, value: str) -> None:
        framesize = parse_framesize(value)
        control_url = build_control_url(self.config.stream_url, "framesize", framesize)
        try:
            response = self._session.get(control_url, timeout=self.config.timeout_seconds)
            response.raise_for_status()
            logging.info("ESP32-CAM framesize set to %s", framesize)
        except requests.RequestException as exc:
            logging.warning("Could not set ESP32-CAM framesize via %s: %s", control_url, exc)

    def _reader_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._consume_stream()
            except requests.RequestException as exc:
                logging.warning("ESP32-CAM stream disconnected: %s", exc)
                self._stop_event.wait(self.config.reconnect_delay_seconds)
            except Exception:
                logging.exception("Unexpected ESP32-CAM reader error")
                self._stop_event.wait(self.config.reconnect_delay_seconds)

    def _consume_stream(self) -> None:
        logging.info("Connecting to ESP32-CAM stream: %s", self.config.stream_url)
        with self._session.get(
            self.config.stream_url,
            stream=True,
            timeout=self.config.timeout_seconds,
            headers={"Cache-Control": "no-cache"},
        ) as response:
            response.raise_for_status()
            buffer = bytearray()

            for chunk in response.iter_content(chunk_size=self.config.request_chunk_size):
                if self._stop_event.is_set():
                    return
                if not chunk:
                    continue

                buffer.extend(chunk)
                self._extract_frames(buffer)

                if len(buffer) > self.config.max_jpeg_bytes:
                    logging.warning("Dropping oversized ESP32-CAM MJPEG buffer")
                    buffer.clear()

    def _extract_frames(self, buffer: bytearray) -> None:
        while True:
            start = buffer.find(b"\xff\xd8")
            end = buffer.find(b"\xff\xd9", start + 2)

            if start < 0:
                buffer.clear()
                return
            if end < 0:
                if start > 0:
                    del buffer[:start]
                return

            jpeg_bytes = bytes(buffer[start : end + 2])
            del buffer[: end + 2]

            encoded = np.frombuffer(jpeg_bytes, dtype=np.uint8)
            frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if frame is None:
                continue

            with self._lock:
                self._frames.append(frame)


class OpenCvReader:
    def __init__(self, source: int | str) -> None:
        self._capture = cv2.VideoCapture(source)
        if not self._capture.isOpened():
            raise RuntimeError(f"Could not open source {source}")

        self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> tuple[bool, np.ndarray | None]:
        return self._capture.read()

    def release(self) -> None:
        self._capture.release()


def parse_source(value: str) -> int | str:
    return int(value) if value.isdigit() else value


def parse_framesize(value: str) -> int:
    normalized = value.strip().lower()
    if normalized.isdigit():
        return int(normalized)
    if normalized in FRAME_SIZES:
        return FRAME_SIZES[normalized]

    valid = ", ".join(sorted(FRAME_SIZES))
    raise ValueError(f"Invalid framesize '{value}'. Use a number or one of: {valid}")


def build_control_url(stream_url: str, variable: str, value: int) -> str:
    parsed = urlparse(stream_url)
    netloc = parsed.netloc or parsed.hostname or ""
    return f"{parsed.scheme}://{netloc}/control?var={variable}&val={value}"


def looks_like_esp32_stream(source: str) -> bool:
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"} and parsed.path.rstrip("/") == "/stream"


def normalize_class_name(value: str) -> str:
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def is_trash_class(class_name: str) -> bool:
    normalized_name = normalize_class_name(class_name)
    normalized_trash_classes = [normalize_class_name(value) for value in TRASH_CLASSES]
    return any(
        trash_class == normalized_name or trash_class in normalized_name
        for trash_class in normalized_trash_classes
    )


def get_class_name(names, class_id: int) -> str:
    if isinstance(names, dict):
        return names.get(class_id, str(class_id))

    if isinstance(names, (list, tuple)) and 0 <= class_id < len(names):
        return str(names[class_id])

    return str(class_id)


def get_detected_trash_classes(result) -> set[str]:
    if result.boxes is None or result.boxes.cls is None:
        return set()

    names = result.names
    detected_trash_classes: set[str] = set()

    for class_id in result.boxes.cls.tolist():
        class_name = get_class_name(names, int(class_id))
        if is_trash_class(class_name):
            detected_trash_classes.add(class_name)

    return detected_trash_classes


def call_servo(servo_url: str, detected_classes: set[str]) -> None:
    class_list = ", ".join(sorted(detected_classes)) or "lixo"
    print(f"[DEBUG] Lixo detectado: {class_list}")
    print(f"[DEBUG] Chamando rota do servo: {servo_url}")

    try:
        response = requests.get(servo_url, timeout=2)
        response.raise_for_status()
        print(f"[OK] Rota /servo chamada com sucesso. Status HTTP: {response.status_code}")
        logging.info("Rota do servo chamada com sucesso: %s | Classes: %s", servo_url, class_list)
    except requests.RequestException as exc:
        print(f"[ERRO] Falha ao chamar a ESP32-CAM: {exc}")
        logging.error("Erro ao chamar a ESP32-CAM em %s: %s", servo_url, exc)


def build_reader(args: argparse.Namespace) -> Esp32MjpegReader | OpenCvReader:
    source = parse_source(args.source)
    use_esp32_reader = args.esp32 or (
        isinstance(source, str) and looks_like_esp32_stream(source)
    )

    if not use_esp32_reader:
        return OpenCvReader(source)

    if not isinstance(source, str):
        raise ValueError("--esp32 requires an HTTP stream URL, for example http://192.168.0.50/stream")

    reader = Esp32MjpegReader(
        Esp32StreamConfig(
            stream_url=source,
            timeout_seconds=args.timeout,
            reconnect_delay_seconds=args.reconnect_delay,
        )
    )

    if args.framesize:
        reader.set_framesize(args.framesize)

    reader.start()
    return reader


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect litter from a camera source or stream.")
    parser.add_argument("--weights", default="runs/trash-detector/weights/best.pt", help="Path to trained weights.")
    parser.add_argument("--source", default="0", help="Camera index or stream URL.")
    parser.add_argument("--imgsz", type=int, default=640, help="Inference image size.")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold.")
    parser.add_argument("--device", default=None, help="Device identifier, for example 0, cuda:0 or cpu.")
    parser.add_argument("--esp32", action="store_true", help="Use the low-latency ESP32-CAM MJPEG reader.")
    parser.add_argument("--framesize", help="ESP32-CAM framesize preset or numeric value, for example qvga or 8.")
    parser.add_argument("--timeout", type=float, default=5.0, help="ESP32-CAM HTTP timeout in seconds.")
    parser.add_argument("--reconnect-delay", type=float, default=1.0, help="Delay between ESP32-CAM reconnect attempts.")
    parser.add_argument("--servo-url", default=SERVO_URL, help="ESP32-CAM servo endpoint.")
    parser.add_argument("--servo-cooldown", type=float, default=SERVO_COOLDOWN_SECONDS, help="Minimum seconds between servo calls.")
    parser.add_argument("--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR"))
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
    )

    model = YOLO(args.weights)
    reader = build_reader(args)
    last_servo_call = 0.0

    try:
        while True:
            success, frame = reader.read()
            if not success:
                time.sleep(0.01)
                continue

            result = model.predict(
                frame,
                imgsz=args.imgsz,
                conf=args.conf,
                device=args.device,
                verbose=False,
            )[0]

            detected_trash_classes = get_detected_trash_classes(result)
            if detected_trash_classes:
                now = time.monotonic()
                if now - last_servo_call >= args.servo_cooldown:
                    call_servo(args.servo_url, detected_trash_classes)
                    last_servo_call = now

            annotated_frame = result.plot()

            cv2.imshow("ecobot-vision", annotated_frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        reader.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
