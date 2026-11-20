"""Computer vision: damage estimation in sidewalk photos (classic OpenCV).

Pipeline (filters, enhancement and segmentation):
 1. Resize to 640 px wide and convert to grayscale.
 2. CLAHE (adaptive histogram equalization) to compensate for shadows and harsh sunlight.
 3. Gaussian filter to reduce the noise of the concrete texture.
 4. Morphological black-hat: highlights DARK and THIN structures (cracks).
 5. Thresholding + morphological opening = mask of candidate cracks.
 6. Probabilistic Hough transform removes long straight lines, which are
    the normal joints between paving slabs and are not damage.
 7. Connected components: discards small blobs (noise).
 8. Pothole segmentation: regions much darker than their surroundings and large in area.
 9. Damage index 0-100 combining % of cracks and % of potholes.

Limitation: this is a heuristic calibrated on SYNTHETIC images (see
scripts/generate_demo_images.py). Real photos with hard shadows, leaves, oil stains
or tactile paving can produce false positives. The result is only used to
reinforce priority and never decides on its own.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np

WIDTH = 640

# Thresholds calibrated on the synthetic calibration set (seed 1).
MODERATE_THRESHOLD = 6
SEVERE_THRESHOLD = 27

LEVELS = ["no visible damage", "moderate", "severe"]


@dataclass
class ImageAnalysis:
    damage_index: float
    level: str
    crack_pct: float
    pothole_pct: float
    joints_removed: int
    crack_components: int

    def to_dict(self):
        return asdict(self)


def decode(content: bytes) -> np.ndarray:
    arr = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("The uploaded file is not a valid image (use JPG or PNG).")
    return img


def reencode_without_metadata(img: np.ndarray, quality: int = 85) -> bytes:
    """cv2.imencode writes only the pixels: EXIF (GPS, device, date) is discarded."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise ValueError("Failed to encode the image.")
    return buf.tobytes()


def _resize(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    if w == WIDTH:
        return img
    scale = WIDTH / w
    return cv2.resize(img, (WIDTH, int(h * scale)), interpolation=cv2.INTER_AREA)


def segment(img: np.ndarray):
    """Returns (crack mask, pothole mask, number of joints removed, resized image, crack components)."""
    img = _resize(img)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    smooth = cv2.GaussianBlur(enhanced, (5, 5), 0)

    # --- cracks: black-hat highlights what is darker and thinner than the structuring element
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17))
    blackhat = cv2.morphologyEx(smooth, cv2.MORPH_BLACKHAT, kernel)
    otsu, _ = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, cracks = cv2.threshold(blackhat, max(otsu, 38), 255, cv2.THRESH_BINARY)
    cracks = cv2.morphologyEx(cracks, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2, 2)))

    # --- paving joints: long straight lines. Hough finds them and we erase them from the mask.
    joints = np.zeros_like(cracks)
    lines = cv2.HoughLinesP(cracks, 1, np.pi / 180, threshold=80,
                            minLineLength=int(img.shape[1] * 0.35), maxLineGap=6)
    n_joints = 0
    if lines is not None:
        for x1, y1, x2, y2 in lines.reshape(-1, 4):  # output shape differs between OpenCV versions
            ang = abs(np.degrees(np.arctan2(y2 - y1, x2 - x1))) % 180
            if min(ang, abs(ang - 90), abs(ang - 180)) < 4:  # almost horizontal/vertical
                cv2.line(joints, (x1, y1), (x2, y2), 255, 7)
                n_joints += 1
    cracks = cv2.subtract(cracks, joints)

    # --- remove small components (concrete grain)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(cracks, connectivity=8)
    min_area = 0.0004 * cracks.size
    clean = np.zeros_like(cracks)
    components = 0
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        elongated = max(w, h) >= 40
        if area >= min_area and elongated:
            clean[labels == i] = 255
            components += 1

    # --- potholes: regions much darker than their surroundings AND wide.
    # A black-hat with a large element highlights everything dark (cracks and potholes);
    # an opening with a 17 px disk "erases" what is thin (cracks, joints) and keeps
    # only what has body, i.e. the potholes.
    large = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (151, 151))
    dark = cv2.morphologyEx(smooth, cv2.MORPH_BLACKHAT, large)
    _, holes = cv2.threshold(dark, 55, 255, cv2.THRESH_BINARY)
    holes = cv2.morphologyEx(holes, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (17, 17)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(holes, connectivity=8)
    potholes = np.zeros_like(holes)
    for i in range(1, n):
        if stats[i, cv2.CC_STAT_AREA] >= 0.004 * holes.size:
            potholes[labels == i] = 255
    clean[potholes > 0] = 0  # the pothole outline does not count as a crack
    return clean, potholes, n_joints, img, components


def analyze(img: np.ndarray) -> tuple[ImageAnalysis, np.ndarray]:
    cracks, potholes, n_joints, base, components = segment(img)
    crack_pct = 100 * np.count_nonzero(cracks) / cracks.size
    pothole_pct = 100 * np.count_nonzero(potholes) / potholes.size
    # Cracks cover little area even when serious, hence the higher weight.
    index = float(min(100.0, crack_pct * 9 + pothole_pct * 6))
    level = "severe" if index >= SEVERE_THRESHOLD else "moderate" if index >= MODERATE_THRESHOLD else "no visible damage"

    overlay = base.copy()
    overlay[cracks > 0] = (40, 40, 230)     # red (BGR)
    overlay[potholes > 0] = (30, 140, 245)  # orange
    overlay = cv2.addWeighted(base, 0.45, overlay, 0.55, 0)
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 42), (25, 25, 25), -1)
    cv2.putText(overlay, f"Damage index: {index:.0f}/100 ({level})", (12, 29),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (255, 255, 255), 2, cv2.LINE_AA)

    return ImageAnalysis(round(index, 1), level, round(crack_pct, 2), round(pothole_pct, 2), n_joints, components), overlay
