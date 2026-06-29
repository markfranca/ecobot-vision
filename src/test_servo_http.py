"""Quick test for the ESP32-CAM /servo route."""

from __future__ import annotations

import requests


ESP32_IP = "192.168.0.87"
SERVO_URL = f"http://{ESP32_IP}/servo"


def main() -> None:
    resposta = requests.get(SERVO_URL, timeout=3)
    print(resposta.text)


if __name__ == "__main__":
    main()
