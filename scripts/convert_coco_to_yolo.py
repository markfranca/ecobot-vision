"""Convert COCO annotations into YOLO label files and copy the matching images."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path


def coco_bbox_to_yolo(bbox: list[float], image_width: int, image_height: int) -> tuple[float, float, float, float]:
    x_min, y_min, width, height = bbox
    x_center = (x_min + width / 2.0) / image_width
    y_center = (y_min + height / 2.0) / image_height
    return x_center, y_center, width / image_width, height / image_height


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert COCO annotations to YOLO labels.")
    parser.add_argument("--annotations", default="data/annotations.json", help="Path to the COCO annotation file.")
    parser.add_argument("--images-dir", default="data", help="Directory containing the source images.")
    parser.add_argument("--output-dir", default="dataset", help="Directory where YOLO files will be written.")
    args = parser.parse_args()

    annotations_path = Path(args.annotations)
    images_dir = Path(args.images_dir)
    output_dir = Path(args.output_dir)
    labels_dir = output_dir / "labels"
    copied_images_dir = output_dir / "images"

    labels_dir.mkdir(parents=True, exist_ok=True)
    copied_images_dir.mkdir(parents=True, exist_ok=True)

    with annotations_path.open("r", encoding="utf-8") as file_handle:
        dataset = json.load(file_handle)

    categories = sorted(dataset.get("categories", []), key=lambda item: item["id"])
    category_id_to_index = {category["id"]: index for index, category in enumerate(categories)}
    classes_file = output_dir / "classes.txt"
    classes_file.write_text("\n".join(category["name"] for category in categories) + "\n", encoding="utf-8")

    annotations_by_image = defaultdict(list)
    for annotation in dataset.get("annotations", []):
        annotations_by_image[annotation["image_id"]].append(annotation)

    for image_info in dataset.get("images", []):
        source_image = images_dir / image_info["file_name"]
        destination_image = copied_images_dir / image_info["file_name"]
        destination_image.parent.mkdir(parents=True, exist_ok=True)

        if source_image.exists() and not destination_image.exists():
            shutil.copy2(source_image, destination_image)

        image_relative_path = Path(image_info["file_name"])
        label_path = labels_dir / image_relative_path.with_suffix(".txt")
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_lines = []

        for annotation in annotations_by_image.get(image_info["id"], []):
            category_index = category_id_to_index.get(annotation["category_id"])
            if category_index is None:
                continue

            bbox = annotation.get("bbox")
            if not bbox or bbox[2] <= 0 or bbox[3] <= 0:
                continue

            x_center, y_center, width, height = coco_bbox_to_yolo(bbox, image_info["width"], image_info["height"])
            label_lines.append(f"{category_index} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")

        label_path.write_text("\n".join(label_lines) + ("\n" if label_lines else ""), encoding="utf-8")


if __name__ == "__main__":
    main()
