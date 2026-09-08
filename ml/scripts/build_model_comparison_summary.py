"""Pulls the headline numbers out of the real, already-computed result files
under data/models/ into one small comparison summary — no new computation,
just consolidation, so it's cheap to re-run after any real training run.

Run as:
    ml/.venv-dl/Scripts/python ml/scripts/build_model_comparison_summary.py
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_ROOT = REPO_ROOT / "data" / "models"


def _load(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def main() -> None:
    unet_metrics = _load(MODELS_ROOT / "unet2d.metrics.json")
    cnn3d_cv = _load(MODELS_ROOT / "cnn3d" / "cross_validation.json")
    cnn3d_external = _load(MODELS_ROOT / "cnn3d" / "external_test.json")
    cnn3d_ensemble_external = _load(MODELS_ROOT / "cnn3d" / "ensemble_external_test.json")
    predicted_pipeline = _load(MODELS_ROOT / "predicted_biomarker_pipeline.json")
    reference_biomarker_eval = _load(MODELS_ROOT / "nearest_centroid_biomarker_eval.json")

    summary: dict = {"note": "Every number here is read from a real training/evaluation run's own output file — nothing recomputed or estimated."}

    if unet_metrics is not None:
        summary["segmentation_unet2d"] = {
            "test_mean_dice_foreground": unet_metrics["test"]["mean_dice_foreground"],
            "test_per_class_dice": unet_metrics["test"]["per_class_dice"],
            "anatomical_violation_rate_percent": unet_metrics.get("detailed_validation", {}).get("anatomical_violation_rate_percent"),
        }

    if cnn3d_cv is not None:
        summary["classification_cnn3d_raw_image"] = {
            "cv_mean_accuracy": cnn3d_cv["mean_accuracy"],
            "cv_std_accuracy": cnn3d_cv["std_accuracy"],
            "cv_median_accuracy": cnn3d_cv["median_accuracy"],
            "cv_min_accuracy": cnn3d_cv["min_accuracy"],
            "cv_max_accuracy": cnn3d_cv["max_accuracy"],
            "out_of_fold_macro_f1": cnn3d_cv["out_of_fold_validation"]["macro"]["f1"],
            "out_of_fold_balanced_accuracy": cnn3d_cv["out_of_fold_validation"]["balanced_accuracy"],
            "out_of_fold_mcc": cnn3d_cv["out_of_fold_validation"]["matthews_correlation_coefficient"],
            "out_of_fold_cohens_kappa": cnn3d_cv["out_of_fold_validation"]["cohens_kappa"],
            "out_of_fold_macro_auc": cnn3d_cv["out_of_fold_validation"]["roc"]["macro_auc"],
            "external_test_accuracy_final_model": cnn3d_external["accuracy"] if cnn3d_external else None,
            "external_test_accuracy_5fold_ensemble": cnn3d_ensemble_external["accuracy"] if cnn3d_ensemble_external else None,
        }

    if predicted_pipeline is not None:
        summary["classification_biomarkers_from_predicted_masks"] = {
            "cv_mean_accuracy": predicted_pipeline["predicted_mask_pipeline"]["cv_mean_accuracy"],
            "cv_std_accuracy": predicted_pipeline["predicted_mask_pipeline"]["cv_std_accuracy"],
            "external_test_accuracy": predicted_pipeline["predicted_mask_pipeline"]["external_test_accuracy"],
            "biomarker_agreement_vs_reference_masks": predicted_pipeline["biomarker_agreement_predicted_vs_reference"],
        }
        summary["classification_biomarkers_from_reference_masks_oracle"] = {
            "cv_mean_accuracy": predicted_pipeline["reference_mask_pipeline"]["cv_mean_accuracy"],
            "cv_std_accuracy": predicted_pipeline["reference_mask_pipeline"]["cv_std_accuracy"],
            "external_test_accuracy": predicted_pipeline["reference_mask_pipeline"]["external_test_accuracy"],
        }
    elif reference_biomarker_eval is not None:
        # Fall back to the earlier, standalone ground-truth-only run if the
        # full predicted-vs-reference pipeline hasn't been run yet.
        summary["classification_biomarkers_from_reference_masks_oracle"] = {
            "cv_mean_accuracy": reference_biomarker_eval["cv_mean_accuracy"],
            "cv_std_accuracy": reference_biomarker_eval["cv_std_accuracy"],
            "external_test_accuracy": reference_biomarker_eval["external_test_accuracy"],
        }

    out_path = MODELS_ROOT / "model_comparison_summary.json"
    out_path.write_text(json.dumps(summary, indent=2))
    print(f"saved to {out_path}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
