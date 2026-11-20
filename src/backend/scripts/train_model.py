"""Trains and evaluates the report classifier."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import StratifiedKFold, cross_val_score
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.svm import LinearSVC

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from clearpath import config  # noqa: E402
from clearpath.governance import anonymize  # noqa: E402
from clearpath.nlp import CATEGORIES, STOPWORDS, normalize  # noqa: E402
import chart_style  # noqa: E402

EVIDENCE_DIR = config.EVIDENCE_DIR
CHARTS_DIR = config.CHARTS_DIR
TIE_MARGIN = 0.01


def word_vectorizer():
    return TfidfVectorizer(preprocessor=normalize, stop_words=sorted(STOPWORDS),
                           ngram_range=(1, 2), min_df=2, sublinear_tf=True)


def char_vectorizer():
    return TfidfVectorizer(preprocessor=normalize, analyzer="char_wb",
                           ngram_range=(3, 5), min_df=2, sublinear_tf=True)


def candidates() -> dict[str, Pipeline]:
    return {
        "Naive Bayes (words)": Pipeline([
            ("tfidf", word_vectorizer()),
            ("clf", MultinomialNB(alpha=0.3)),
        ]),
        "Logistic Regression (words + characters)": Pipeline([
            ("tfidf", FeatureUnion([("words", word_vectorizer()), ("chars", char_vectorizer())])),
            ("clf", LogisticRegression(C=8, max_iter=3000)),
        ]),
        "Calibrated linear SVM (words + characters)": Pipeline([
            ("tfidf", FeatureUnion([("words", word_vectorizer()), ("chars", char_vectorizer())])),
            ("clf", CalibratedClassifierCV(LinearSVC(C=0.8), cv=3)),
        ]),
    }


def comparison_chart(res: pd.DataFrame, path: Path):
    plt = chart_style.apply()
    fig, ax = plt.subplots(figsize=(8, 3.6))
    names = [n.replace(" (", "\n(") for n in res["model"]]
    y = np.arange(len(res))
    h = 0.36
    b1 = ax.barh(y - h / 2 - 0.01, res["f1_cv"], height=h, color=chart_style.SERIES[0], label="Cross-validation (synthetic)")
    b2 = ax.barh(y + h / 2 + 0.01, res["f1_blind_test"], height=h, color=chart_style.SERIES[1], label="Blind test (hand-written)")
    for bars in (b1, b2):
        for b in bars:
            ax.text(b.get_width() + 0.01, b.get_y() + b.get_height() / 2, f"{b.get_width():.2f}",
                    va="center", fontsize=9, color=chart_style.INK_2)
    ax.set_yticks(y, names)
    ax.invert_yaxis()
    ax.set_xlim(0, 1.12)
    ax.set_xlabel("Macro F1")
    ax.grid(axis="y", visible=False)
    ax.set_axisbelow(True)
    ax.set_title("Comparison of report classification models", pad=28)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def confusion_chart(y_true, y_pred, labels, path: Path):
    plt = chart_style.apply()
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(7.2, 5.6))
    ax.imshow(cm, cmap=chart_style.BLUE_SEQ, vmin=0, vmax=cm.max())
    names = [CATEGORIES[r] for r in labels]
    ax.set_xticks(range(len(labels)), names, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)), names)
    ax.grid(False)
    for i in range(len(labels)):
        for j in range(len(labels)):
            if cm[i, j]:
                color = "#ffffff" if cm[i, j] > cm.max() * 0.55 else chart_style.INK
                ax.text(j, i, cm[i, j], ha="center", va="center", color=color, fontsize=10)
    ax.set_xlabel("Predicted category")
    ax.set_ylabel("True category")
    ax.set_title("Confusion matrix: blind test (60 reports)")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    train = pd.read_csv(config.DATA_DIR / "reports_train.csv")
    blind = pd.read_csv(config.DATA_DIR / "reports_blind_test.csv")
    # The model is trained on ALREADY anonymized text, exactly as it runs in the API.
    X = train["text"].map(lambda t: anonymize(t).text)
    y = train["category"]
    X_blind = blind["text"].map(lambda t: anonymize(t).text)
    y_blind = blind["category"]

    print(f"Train: {len(train)} synthetic reports | Blind test: {len(blind)} reports")
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    rows, fitted = [], {}
    for name, pipe in candidates().items():
        f1_cv = cross_val_score(pipe, X, y, cv=skf, scoring="f1_macro")
        pipe.fit(X, y)
        pred = pipe.predict(X_blind)
        fitted[name] = pipe
        rows.append({
            "model": name,
            "f1_cv": round(f1_cv.mean(), 4),
            "f1_cv_std": round(f1_cv.std(), 4),
            "f1_blind_test": round(f1_score(y_blind, pred, average="macro"), 4),
            "accuracy_blind_test": round(accuracy_score(y_blind, pred), 4),
        })
        print(f"- {name}: CV F1={f1_cv.mean():.3f}±{f1_cv.std():.3f} | blind F1={rows[-1]['f1_blind_test']:.3f}")

    res = pd.DataFrame(rows)
    # Selection rule: best blind-test F1. Differences below TIE_MARGIN (less than one sentence
    # out of 60) are treated as a tie, broken by the cross-validation F1.
    top_f1 = res["f1_blind_test"].max()
    tied = res[res["f1_blind_test"] >= top_f1 - TIE_MARGIN]
    best = tied.sort_values(["f1_cv", "f1_blind_test"], ascending=False).iloc[0]["model"]
    model = fitted[best]
    pred = model.predict(X_blind)
    print(f"\nChosen model: {best}\n")
    report = classification_report(y_blind, pred, output_dict=True, zero_division=0)
    print(classification_report(y_blind, pred, zero_division=0))

    errors = blind.assign(predicted=pred)[lambda d: d.category != d.predicted]

    config.MODEL_FILE.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, config.MODEL_FILE)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    res.to_csv(EVIDENCE_DIR / "nlp_model_comparison.csv", index=False)
    errors.to_csv(EVIDENCE_DIR / "nlp_blind_test_errors.csv", index=False)
    (EVIDENCE_DIR / "nlp_metrics.json").write_text(json.dumps({
        "chosen_model": best,
        "comparison": rows,
        "blind_test_report": report,
        "n_train": len(train),
        "n_blind_test": len(blind),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    comparison_chart(res, CHARTS_DIR / "nlp_model_comparison.png")
    confusion_chart(y_blind, pred, list(CATEGORIES), CHARTS_DIR / "nlp_confusion_matrix.png")
    print(f"Model saved to {config.MODEL_FILE}")
    print(f"Evidence in {EVIDENCE_DIR} and {CHARTS_DIR}")


if __name__ == "__main__":
    main()
