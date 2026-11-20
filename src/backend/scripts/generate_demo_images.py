"""Generates SYNTHETIC sidewalk images to calibrate and test the vision module.

Why synthetic: we did not find a public, labeled dataset of Brazilian sidewalks
with a clear license. Generating the images gives full control over the label
(we know exactly where the cracks are), but they are "cleaner" than real photos.
This limitation is documented in the report.

Two sets, with different seeds:
- calibration (seed 1): used to choose the damage index thresholds;
- test (seed 2): used ONLY to measure the final performance.

Usage:
    uv run python scripts/generate_demo_images.py
"""
from __future__ import annotations

import csv
from pathlib import Path

import cv2
import numpy as np

SRC_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = SRC_ROOT / "data" / "demo_images"
H, W = 480, 640
PER_CLASS = 15
LEVELS = ["no visible damage", "moderate", "severe"]


def concrete_texture(rng: np.random.Generator) -> np.ndarray:
    base = rng.uniform(140, 195)
    grain = rng.normal(0, 9, (H, W))
    stains = cv2.GaussianBlur(rng.normal(0, 30, (H // 8, W // 8)), (0, 0), 2)
    stains = cv2.resize(stains, (W, H), interpolation=cv2.INTER_CUBIC)
    gx = np.linspace(-1, 1, W)[None, :] * rng.uniform(-18, 18)
    gy = np.linspace(-1, 1, H)[:, None] * rng.uniform(-18, 18)
    img = base + grain + stains * 0.6 + gx + gy
    color = np.stack([img * rng.uniform(0.95, 1.0), img, img * rng.uniform(0.97, 1.03)], axis=-1)
    return np.clip(color, 0, 255).astype(np.uint8)


def joints(img: np.ndarray, rng: np.random.Generator):
    step = int(rng.integers(110, 170))
    dark = int(rng.integers(55, 85))
    off = int(rng.integers(0, step))
    for x in range(off, W, step):
        cv2.line(img, (x, 0), (x, H), (dark,) * 3, 2)
    for y in range(off // 2, H, step):
        cv2.line(img, (0, y), (W, y), (dark,) * 3, 2)


def crack(img: np.ndarray, rng: np.random.Generator):
    x, y = rng.uniform(W * 0.15, W * 0.85), rng.uniform(H * 0.15, H * 0.85)
    ang = rng.uniform(0, 2 * np.pi)
    points = [(x, y)]
    for _ in range(int(rng.integers(25, 60))):
        ang += rng.normal(0, 0.45)
        nx, ny = x + 9 * np.cos(ang), y + 9 * np.sin(ang)
        if not (10 < nx < W - 10 and 10 < ny < H - 10):  # "bounce" at the border so the crack stays visible
            ang += np.pi
            nx, ny = x + 9 * np.cos(ang), y + 9 * np.sin(ang)
        x, y = nx, ny
        points.append((x, y))
    pts = np.array(points, np.int32)
    thickness = int(rng.integers(2, 5))
    dark = int(rng.integers(25, 60))
    cv2.polylines(img, [pts], False, (dark,) * 3, thickness, cv2.LINE_AA)
    # branch
    if rng.random() < 0.6:
        i = int(rng.integers(3, len(pts) - 2))
        branch = pts[i:i + int(rng.integers(5, 15))] + rng.integers(-25, 25, (1, 2))
        cv2.polylines(img, [np.vstack([pts[i:i + 1], branch])], False, (dark + 10,) * 3, max(1, thickness - 1), cv2.LINE_AA)


def pothole(img: np.ndarray, rng: np.random.Generator):
    cx, cy = int(rng.uniform(100, W - 100)), int(rng.uniform(100, H - 100))
    ang = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    radius = rng.uniform(35, 75) * (1 + 0.25 * np.sin(ang * rng.integers(2, 5) + rng.uniform(0, 6)))
    pts = np.stack([cx + radius * np.cos(ang), cy + radius * 0.7 * np.sin(ang)], axis=1).astype(np.int32)
    mask = np.zeros((H, W), np.uint8)
    cv2.fillPoly(mask, [pts], 255)
    mask = cv2.GaussianBlur(mask, (9, 9), 0) / 255.0
    bottom = rng.uniform(35, 65)
    for c in range(3):
        img[..., c] = (img[..., c] * (1 - mask) + (bottom + rng.normal(0, 6, (H, W))) * mask).clip(0, 255)


def light_stain(img: np.ndarray, rng: np.random.Generator):
    """Dirt stain: only slightly darker, NOT damage (tests false positives)."""
    cx, cy = int(rng.uniform(50, W - 50)), int(rng.uniform(50, H - 50))
    over = img.copy()
    cv2.ellipse(over, (cx, cy), (int(rng.uniform(20, 60)), int(rng.uniform(15, 40))), rng.uniform(0, 180), 0, 360,
                (int(img[cy, cx, 0]) - 20,) * 3, -1)
    over = cv2.GaussianBlur(over, (21, 21), 0)
    img[:] = cv2.addWeighted(img, 0.4, over, 0.6, 0)


def generate(level: str, rng: np.random.Generator) -> np.ndarray:
    img = concrete_texture(rng)
    if rng.random() < 0.6:
        joints(img, rng)
    for _ in range(int(rng.integers(0, 3))):
        light_stain(img, rng)
    if level == "moderate":
        for _ in range(int(rng.integers(1, 3))):
            crack(img, rng)
    elif level == "severe":
        for _ in range(int(rng.integers(3, 6))):
            crack(img, rng)
        for _ in range(int(rng.integers(1, 3))):
            pothole(img, rng)
    return cv2.GaussianBlur(img, (3, 3), 0)


def file_name(level: str, i: int) -> str:
    return f"{level.replace(' ', '_')}_{i:02d}.jpg"


def main():
    for subset, seed in (("calibration", 1), ("test", 2)):
        rng = np.random.default_rng(seed)
        folder = OUTPUT_DIR / subset
        folder.mkdir(parents=True, exist_ok=True)
        rows = []
        for level in LEVELS:
            for i in range(PER_CLASS):
                name = file_name(level, i)
                cv2.imwrite(str(folder / name), generate(level, rng), [cv2.IMWRITE_JPEG_QUALITY, 88])
                rows.append({"file": name, "true_level": level, "source": "synthetic"})
        with (folder / "labels.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["file", "true_level", "source"])
            w.writeheader()
            w.writerows(rows)
        print(f"{len(rows)} images in {folder}")


if __name__ == "__main__":
    main()
