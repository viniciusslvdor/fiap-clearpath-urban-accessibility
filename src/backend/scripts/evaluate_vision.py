"""Evaluates the vision module on the synthetic images.

    uv run python scripts/evaluate_vision.py calibration   # used to tune the thresholds
    uv run python scripts/evaluate_vision.py test          # final result (never tune with it!)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from clearpath import config, vision  # noqa: E402
import chart_style  # noqa: E402
from generate_demo_images import file_name  # noqa: E402

LEVELS = vision.LEVELS


def main(subset: str):
    folder = config.DATA_DIR / "demo_images" / subset
    labels = pd.read_csv(folder / "labels.csv")
    rows = []
    for _, r in labels.iterrows():
        analysis, _ = vision.analyze(cv2.imread(str(folder / r.file)))
        rows.append({**r.to_dict(), **analysis.to_dict()})
    df = pd.DataFrame(rows)
    acc = accuracy_score(df.true_level, df.level)
    print(df.groupby("true_level")[["damage_index", "crack_pct", "pothole_pct", "joints_removed"]].describe().T.round(2).to_string())
    print(f"\nAccuracy ({subset}): {acc:.3f}")
    cm = confusion_matrix(df.true_level, df.level, labels=LEVELS)
    print(pd.DataFrame(cm, index=[f"true:{n}" for n in LEVELS], columns=[f"pred:{n}" for n in LEVELS]).to_string())

    if subset == "calibration":
        # Grid search of the thresholds ONLY on the calibration set.
        best = max(
            ((m, s, accuracy_score(df.true_level, np.where(df.damage_index >= s, "severe",
                                   np.where(df.damage_index >= m, "moderate", "no visible damage"))))
             for m in range(2, 30) for s in range(m + 5, 80)),
            key=lambda t: (round(t[2], 3), -abs((t[0] + t[1]) / 2 - 25)),
        )
        print(f"Suggested thresholds -> moderate >= {best[0]}, severe >= {best[1]} (calibration accuracy {best[2]:.3f})")

    if subset == "test":
        evidence, charts = config.EVIDENCE_DIR, config.CHARTS_DIR
        evidence.mkdir(parents=True, exist_ok=True)
        charts.mkdir(parents=True, exist_ok=True)
        df.to_csv(evidence / "vision_test_results.csv", index=False)
        (evidence / "vision_metrics.json").write_text(json.dumps({
            "test_accuracy": round(acc, 4),
            "confusion_matrix": {"labels": LEVELS, "values": cm.tolist()},
            "thresholds": {"moderate": vision.MODERATE_THRESHOLD, "severe": vision.SEVERE_THRESHOLD},
            "n_images": len(df),
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        scatter_chart(df, charts / "vision_index_by_class.png")
        examples(folder, charts / "vision_examples.png")
        print(f"Evidence saved to {evidence} and {charts}")


def scatter_chart(df: pd.DataFrame, path: Path):
    plt = chart_style.apply()
    fig, ax = plt.subplots(figsize=(7.5, 3.4))
    rng = np.random.default_rng(0)
    for i, level in enumerate(LEVELS):
        sub = df[df.true_level == level]
        ax.scatter(sub.damage_index, i + rng.uniform(-0.12, 0.12, len(sub)), s=46,
                   color=chart_style.SERIES[i], edgecolor=chart_style.SURFACE, linewidth=1.5, zorder=3)
    for lim, name in ((vision.MODERATE_THRESHOLD, "moderate threshold"), (vision.SEVERE_THRESHOLD, "severe threshold")):
        ax.axvline(lim, color=chart_style.MUTED, linestyle="--", linewidth=1)
        ax.text(lim + 1, 2.45, name, color=chart_style.INK_2, fontsize=8)
    ax.set_yticks(range(3), [f"True: {n}" for n in LEVELS])
    ax.set_ylim(-0.5, 2.7)
    ax.set_xlim(-2, 102)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("Computed damage index (0-100)")
    ax.set_title("Damage index by true class: synthetic test set (45 images)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def examples(folder: Path, path: Path):
    """Original vs segmentation panel for one image of each class."""
    rows = []
    for level in LEVELS:
        img = cv2.imread(str(folder / file_name(level, 0)))
        _, overlay = vision.analyze(img)
        orig = cv2.resize(img, (overlay.shape[1], overlay.shape[0]))
        rows.append(np.hstack([orig, np.full((orig.shape[0], 8, 3), 252, np.uint8), overlay]))
    sep = np.full((8, rows[0].shape[1], 3), 252, np.uint8)
    panel = np.vstack([x for r in rows for x in (r, sep)][:-1])
    cv2.imwrite(str(path), cv2.resize(panel, None, fx=0.6, fy=0.6, interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "calibration")
