"""Runs the genuinely end-to-end "raw image -> U-Net mask -> biomarkers ->
nearest-centroid diagnosis" pipeline on real ACDC data, using the U-Net
weights already trained by train_segmentation.py. Reports, side by side:

1. How much measurement error the segmentation model introduces into each
   clinical biomarker (predicted-mask vs. reference-mask features).
2. The nearest-centroid classifier's real accuracy when every feature comes
   from the model's own predictions — no ground truth involved anywhere in
   this number — compared against the same classifier fit on reference-mask
   features (the oracle upper bound already computed by
   compare_biomarker_classifier.py).

Run as:
    ml/.venv-dl/Scripts/python ml/scripts/run_predicted_biomarker_pipeline.py
"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
sys.path.insert(0, str(ML_ROOT))

from cardiac_ai_ml.dl.acdc_dataset import discover_patients  # noqa: E402
from cardiac_ai_ml.dl.models import build_unet2d  # noqa: E402
from cardiac_ai_ml.dl.predicted_biomarker_pipeline import (  # noqa: E402
    biomarker_agreement_report,
    predicted_biomarker_features,
    reference_biomarker_features,
    run_nearest_centroid_cv_and_external_test,
)

DATA_ROOT = REPO_ROOT / "data"
TRAIN_ROOT = DATA_ROOT / "acdc-raw" / "ACDC" / "database" / "training"
TEST_ROOT = DATA_ROOT / "acdc-raw" / "ACDC" / "database" / "testing"
UNET_WEIGHTS = DATA_ROOT / "models" / "unet2d.pt"
OUT_PATH = DATA_ROOT / "models" / "predicted_biomarker_pipeline.json"


def main() -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}", flush=True)

    if not UNET_WEIGHTS.exists():
        raise SystemExit(f"{UNET_WEIGHTS} not found — train the U-Net first (train_segmentation.py)")

    model = build_unet2d().to(device)
    model.load_state_dict(torch.load(UNET_WEIGHTS, map_location=device))
    model.eval()

    train_patients = discover_patients(TRAIN_ROOT)
    test_patients = discover_patients(TEST_ROOT)
    all_patients = train_patients + test_patients
    print(f"{len(train_patients)} training patients, {len(test_patients)} testing patients", flush=True)

    print("computing reference-mask biomarkers for all patients...", flush=True)
    reference_features = {p.patient_id: reference_biomarker_features(p) for p in all_patients}

    print("running U-Net inference + predicted-mask biomarkers for all patients (this is the slow step)...", flush=True)
    predicted_features = {}
    for i, patient in enumerate(all_patients, start=1):
        predicted_features[patient.patient_id] = predicted_biomarker_features(patient, model, device)
        if i % 25 == 0 or i == len(all_patients):
            print(f"  {i}/{len(all_patients)} patients done", flush=True)

    print("computing biomarker agreement (predicted vs reference masks)...", flush=True)
    agreement = biomarker_agreement_report(predicted_features, reference_features)
    for feature_name, result in agreement.items():
        print(
            f"  {feature_name}: MAE={result.mae:.2f}  RMSE={result.rmse:.2f}  bias={result.bias:.2f}  "
            f"ICC={result.icc:.3f}  Pearson r={result.pearson_r:.3f}",
            flush=True,
        )

    print("evaluating nearest-centroid classifier on PREDICTED-mask features (k=5, seed=42)...", flush=True)
    predicted_pipeline_result = run_nearest_centroid_cv_and_external_test(
        train_patients, test_patients, predicted_features, predicted_features, k=5, seed=42
    )
    print(
        f"  PREDICTED-mask pipeline: CV accuracy={predicted_pipeline_result['cv_mean_accuracy']:.4f} "
        f"+/- {predicted_pipeline_result['cv_std_accuracy']:.4f}  "
        f"external test={predicted_pipeline_result['external_test_accuracy']:.4f}",
        flush=True,
    )

    print("evaluating nearest-centroid classifier on REFERENCE-mask features (same folds, for comparison)...", flush=True)
    reference_pipeline_result = run_nearest_centroid_cv_and_external_test(
        train_patients, test_patients, reference_features, reference_features, k=5, seed=42
    )
    print(
        f"  REFERENCE-mask pipeline: CV accuracy={reference_pipeline_result['cv_mean_accuracy']:.4f} "
        f"+/- {reference_pipeline_result['cv_std_accuracy']:.4f}  "
        f"external test={reference_pipeline_result['external_test_accuracy']:.4f}",
        flush=True,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "patient_count": len(all_patients),
                "biomarker_agreement_predicted_vs_reference": {name: asdict(result) for name, result in agreement.items()},
                "predicted_mask_pipeline": predicted_pipeline_result,
                "reference_mask_pipeline": reference_pipeline_result,
                "macro_f1_and_balanced_accuracy_note": (
                    "cardiac_ai_ml.training.evaluate reports plain accuracy and per-class accuracy only "
                    "(see EvaluationResult) — no macro-F1/balanced-accuracy field exists on this path today."
                ),
            },
            indent=2,
        )
    )
    print(f"saved to {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
