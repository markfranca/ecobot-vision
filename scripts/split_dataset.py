"""Split a YOLO dataset into train, valid and test sets and write data.yaml."""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def copy_pair(
    image_path: Path,
    label_path: Path,
    relative_image_path: Path,
    destination_images: Path,
    destination_labels: Path,
) -> None:
    destination_image = destination_images / relative_image_path
    destination_label = destination_labels / relative_image_path.with_suffix(".txt")
    destination_image.parent.mkdir(parents=True, exist_ok=True)
    destination_label.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(image_path, destination_image)
    if label_path.exists():
        shutil.copy2(label_path, destination_label)
    else:
        destination_label.write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split a YOLO dataset into train/valid/test.")
    parser.add_argument("--dataset-root", default="dataset", help="Dataset root directory.")
    parser.add_argument("--source-images", default="dataset/images", help="Directory with unsplit images.")
    parser.add_argument("--source-labels", default="dataset/labels", help="Directory with unsplit labels.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Training split ratio.")
    parser.add_argument("--valid-ratio", type=float, default=0.1, help="Validation split ratio.")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Test split ratio.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    args = parser.parse_args()

    dataset_root = Path(args.dataset_root)
    source_images = Path(args.source_images)
    source_labels = Path(args.source_labels)

    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    image_files = sorted(
        path for path in source_images.rglob("*")
        if path.is_file() and path.suffix.lower() in image_extensions
    )
    random.Random(args.seed).shuffle(image_files)

    total_ratio = args.train_ratio + args.valid_ratio + args.test_ratio
    if total_ratio <= 0:
        raise ValueError("Split ratios must sum to a positive value.")

    train_count = int(len(image_files) * args.train_ratio / total_ratio)
    valid_count = int(len(image_files) * args.valid_ratio / total_ratio)
    test_count = len(image_files) - train_count - valid_count

    train_files = image_files[:train_count]
    valid_files = image_files[train_count:train_count + valid_count]
    test_files = image_files[train_count + valid_count:train_count + valid_count + test_count]

    split_map = {
        "train": train_files,
        "valid": valid_files,
        "test": test_files,
    }

    for split_name, files in split_map.items():
        for image_path in files:
            relative_image_path = image_path.relative_to(source_images)
            label_path = source_labels / relative_image_path.with_suffix(".txt")
            copy_pair(
                image_path,
                label_path,
                relative_image_path,
                dataset_root / split_name / "images",
                dataset_root / split_name / "labels",
            )

    if source_images.parent == dataset_root and source_images.exists():
        shutil.rmtree(source_images)
    if source_labels.parent == dataset_root and source_labels.exists():
        shutil.rmtree(source_labels)

    classes_file = dataset_root / "classes.txt"
    if not classes_file.exists():
        raise FileNotFoundError(f"Missing classes file: {classes_file}")

    class_names = [line.strip() for line in classes_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    yaml_lines = [
        f"path: {dataset_root.resolve()}",
        "train: train/images",
        "val: valid/images",
        "test: test/images",
        "names:",
    ]
    for index, class_name in enumerate(class_names):
        yaml_lines.append(f"  {index}: {class_name}")

    (dataset_root / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
