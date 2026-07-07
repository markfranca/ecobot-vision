"""Read JPEG frames sent by an ESP32-CAM over a framed serial protocol."""

from __future__ import annotations

import logging
import struct
import time

import cv2
import numpy as np
import serial


START = b"\xAA\x55"
END = b"\x55\xAA"


class SerialCameraReader:
    def __init__(
        self,
        port: str,
        baudrate: int,
        timeout: float = 5.0,
        max_frame_size: int = 200_000,
        sync_timeout: float = 2.0,
    ) -> None:
        self.max_frame_size = max_frame_size
        self.sync_timeout = sync_timeout
        self.last_frame_size = 0
        self.bytes_scanned = 0
        self.sync_timeouts = 0
        self.invalid_frame_sizes = 0
        self.invalid_end_markers = 0
        self.invalid_jpegs = 0
        self.start_markers_found = 0
        self.partial_frame_size = 0
        self.buffer_size = 0
        self._buffer = bytearray()
        self._serial = serial.Serial(port, baudrate, timeout=timeout)

    def read(self) -> tuple[bool, np.ndarray | None]:
        frame = self._read_frame_from_serial()
        return frame is not None, frame

    def release(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    def reset_input_buffer(self) -> None:
        self._serial.reset_input_buffer()
        self._buffer.clear()
        self.partial_frame_size = 0
        self.buffer_size = 0

    def _read_frame_from_serial(self) -> np.ndarray | None:
        deadline = time.monotonic() + self.sync_timeout

        while time.monotonic() < deadline:
            self._discard_until_start()
            frame = self._try_decode_buffered_frame()
            if frame is not None:
                return frame

            try:
                bytes_to_read = max(self._serial.in_waiting, 1)
                chunk = self._serial.read(bytes_to_read)
            except serial.SerialException as exc:
                logging.error("Erro lendo serial da camera: %s", exc)
                return None

            if not chunk:
                continue

            self.bytes_scanned += len(chunk)
            self._buffer.extend(chunk)
            self.buffer_size = len(self._buffer)

        self.sync_timeouts += 1
        return None

    def _discard_until_start(self) -> None:
        start_index = self._buffer.find(START)
        if start_index > 0:
            del self._buffer[:start_index]
        elif start_index < 0 and len(self._buffer) > 1:
            # Keep one byte in case it is the first byte of START split across reads.
            del self._buffer[:-1]
        self.buffer_size = len(self._buffer)

    def _try_decode_buffered_frame(self) -> np.ndarray | None:
        if len(self._buffer) < 6:
            return None
        if not self._buffer.startswith(START):
            return None

        self.start_markers_found += 1
        frame_size = struct.unpack("<I", self._buffer[2:6])[0]
        if frame_size <= 0 or frame_size > self.max_frame_size:
            self.invalid_frame_sizes += 1
            self.partial_frame_size = 0
            logging.debug("Tamanho de JPEG invalido recebido: %d", frame_size)
            del self._buffer[:1]
            return None

        packet_size = 2 + 4 + frame_size + 2
        if len(self._buffer) < packet_size:
            self.partial_frame_size = frame_size
            self.buffer_size = len(self._buffer)
            return None

        jpeg_bytes = bytes(self._buffer[6 : 6 + frame_size])
        end_marker = bytes(self._buffer[6 + frame_size : packet_size])

        if end_marker != END:
            self.invalid_end_markers += 1
            self.partial_frame_size = 0
            logging.debug(
                "Marcador END invalido para JPEG de %d bytes: %s",
                frame_size,
                end_marker.hex(" "),
            )
            del self._buffer[:1]
            return None

        del self._buffer[:packet_size]
        self.partial_frame_size = 0
        self.buffer_size = len(self._buffer)

        if not jpeg_bytes.startswith(b"\xff\xd8"):
            self.invalid_jpegs += 1
            logging.debug("JPEG recebido sem marcador SOI")
            return None

        image_array = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
        if frame is None:
            self.invalid_jpegs += 1
            logging.debug("JPEG invalido recebido; buscando proximo frame")
            return None

        self.last_frame_size = frame_size
        return frame
