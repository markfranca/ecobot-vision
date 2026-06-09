"""Download images referenced by a COCO annotation file."""

from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image


def download_image(url: str, destination: Path) -> None:
    response = requests.get(url, timeout=60)
    response.raise_for_status()

    image = Image.open(BytesIO(response.content))
    destination.parent.mkdir(parents=True, exist_ok=True)

    exif = image.info.get("exif")
    if exif:
        image.save(destination, exif=exif)
    else:
        image.save(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download images from a COCO JSON file.")
    parser.add_argument("--annotations", default="data/annotations.json", help="Path to a COCO annotation file.")
    parser.add_argument("--output-dir", default="data", help="Directory where images will be saved.")
    parser.add_argument(
        "--url-key",
        default="flickr_url",
        choices=["flickr_url", "flickr_640_url"],
        help="Image URL field to use from the COCO JSON.",
    )
    args = parser.parse_args()

    annotations_path = Path(args.annotations)
    output_dir = Path(args.output_dir)

    with annotations_path.open("r", encoding="utf-8") as file_handle:
        dataset = json.load(file_handle)

    images = dataset.get("images", [])
    total = len(images)

    for index, image_info in enumerate(images, start=1):
        file_name = image_info["file_name"]
        image_url = image_info.get(args.url_key)
        if not image_url:
            continue

        destination = output_dir / file_name
        if destination.exists():
            continue

        try:
            download_image(image_url, destination)
        except Exception as error:
            print(f"[skip] {file_name}: {error}")

        progress = int(30 * index / max(total, 1))
        bar = "=" * progress + "." * (30 - progress)
        print(f"Downloading: [{bar}] {index}/{total}", end="\r")

    print("\nFinished")


if __name__ == "__main__":
    main()