"""Offline explainability showcase for EPIC-1 (Grad-CAM + LIME/Shapley panel).

Decision: exposed as an offline script here, NOT a new API endpoint — EPIC-3
("Grad-CAM integrado en el flujo de analisis servido") is explicitly the
step that wires this into the real inference API, and it's blocked on
EPIC-2 (serving the real models from the API at all), which doesn't exist
yet; an endpoint now would be premature and disconnected from any real
caller. See docs/epics/EPIC-1-explicabilidad-gradcam-lime.md.

Runs, on real checkpoints and real ACDC data already on disk:

1. Seg-Grad-CAM over the trained U-Net (`data/models/unet2d.pt`) for one
   real test patient's ED slice, for every structure (LV/RV/MYO) the model
   actually predicted.
2. 3D Grad-CAM over the trained CNN3D (`data/models/cnn3d/cnn3d.pt`) for
   the same test patient's ED/ES volume.
3. The pedagogical LIME-vs-Shapley comparison panel (see ADR-3) over the
   nearest-centroid biomarker classifier, fit on real biomarkers computed
   from real ACDC training masks, explained for the same test patient.

Saves PNG heatmap overlays plus a summary JSON (attribution stats, not the
full arrays — those are visualized in the PNGs instead) under
data/models/explainability/.

Run as:
    ml/.venv-dl/Scripts/python -u ml/scripts/run_explainability_showcase.py
"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import torch

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_ROOT = REPO_ROOT / "ml"
sys.path.insert(0, str(ML_ROOT))

from cardiac_ai_ml.classification import DiagnosisClass  # noqa: E402
from cardiac_ai_ml.dl.acdc_dataset import discover_patients  # noqa: E402
from cardiac_ai_ml.dl.classification_dataset import AcdcVolumeDataset  # noqa: E402
from cardiac_ai_ml.dl.explainability import (  # noqa: E402
    grad_cam_3d,
    load_single_slice_tensor,
    seg_grad_cam_all_structures,
)
from cardiac_ai_ml.dl.lime_shapley_panel import (  # noqa: E402
    build_explanation_panel,
    build_lime_explainer,
    real_background_biomarker_features,
)
from cardiac_ai_ml.dl.models import build_cnn3d, build_unet2d  # noqa: E402
from cardiac_ai_ml.dl.predicted_biomarker_pipeline import reference_biomarker_features  # noqa: E402
from cardiac_ai_ml.training import TrainingCase, fit_nearest_centroid  # noqa: E402

DATA_ROOT = REPO_ROOT / "data"
TRAIN_ROOT = DATA_ROOT / "acdc-raw" / "ACDC" / "database" / "training"
TEST_ROOT = DATA_ROOT / "acdc-raw" / "ACDC" / "database" / "testing"
UNET_WEIGHTS = DATA_ROOT / "models" / "unet2d.pt"
CNN3D_WEIGHTS = DATA_ROOT / "models" / "cnn3d" / "cnn3d.pt"
OUT_DIR = DATA_ROOT / "models" / "explainability"


def _save_seg_gradcam_overlay(image: np.ndarray, attribution: np.ndarray, structure: str, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    axes[0].imshow(image, cmap="gray")
    axes[0].set_title("MRI slice")
    axes[0].axis("off")
    axes[1].imshow(image, cmap="gray")
    axes[1].imshow(attribution, cmap="jet", alpha=0.45)
    axes[1].set_title(f"Seg-Grad-CAM: {structure}")
    axes[1].axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _save_cnn3d_gradcam_overlay(volume_channel: np.ndarray, attribution: np.ndarray, z_index: int, path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8, 4))
    slice_image = volume_channel[:, :, z_index]
    slice_cam = attribution[:, :, z_index]
    axes[0].imshow(slice_image, cmap="gray")
    axes[0].set_title(f"ED slice z={z_index}")
    axes[0].axis("off")
    axes[1].imshow(slice_image, cmap="gray")
    axes[1].imshow(slice_cam, cmap="jet", alpha=0.45)
    axes[1].set_title("3D Grad-CAM (ED/ES combined)")
    axes[1].axis("off")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def run_unet_showcase(device: torch.device) -> dict:
    print("=== U-Net Seg-Grad-CAM ===", flush=True)
    if not UNET_WEIGHTS.exists():
        raise SystemExit(f"{UNET_WEIGHTS} not found — train the U-Net first")

    model = build_unet2d().to(device)
    model.load_state_dict(torch.load(UNET_WEIGHTS, map_location=device))
    model.eval()

    test_patients = discover_patients(TEST_ROOT)
    patient = test_patients[0]
    print(f"patient: {patient.patient_id} ({patient.diagnosis_class})", flush=True)

    import nibabel as nib

    n_slices = nib.load(str(patient.ed_image_path)).shape[2]
    mid_slice = n_slices // 2
    image_tensor = load_single_slice_tensor(str(patient.ed_image_path), mid_slice, device=device)

    results = seg_grad_cam_all_structures(model, image_tensor)
    print(f"structures with a genuine Grad-CAM map (nonzero predicted pixels): {list(results)}", flush=True)

    summary = {}
    image_np = image_tensor.squeeze(0).squeeze(0).cpu().numpy()
    for structure, result in results.items():
        out_path = OUT_DIR / f"unet_gradcam_{patient.patient_id}_{structure}.png"
        _save_seg_gradcam_overlay(image_np, result.attribution, structure, out_path)
        summary[structure] = {
            "predicted_pixel_count": result.predicted_pixel_count,
            "layer_name": result.layer_name,
            "attribution_mean": float(result.attribution.mean()),
            "attribution_max": float(result.attribution.max()),
            "png_path": str(out_path.relative_to(REPO_ROOT)),
        }
        print(
            f"  {structure}: predicted_pixels={result.predicted_pixel_count} "
            f"attribution_mean={summary[structure]['attribution_mean']:.4f} -> {out_path.name}",
            flush=True,
        )

    return {"patient_id": patient.patient_id, "slice_index": mid_slice, "structures": summary}


def run_cnn3d_showcase(device: torch.device) -> dict:
    print("=== CNN3D 3D Grad-CAM ===", flush=True)
    if not CNN3D_WEIGHTS.exists():
        raise SystemExit(f"{CNN3D_WEIGHTS} not found — train the CNN3D first")

    model = build_cnn3d().to(device)
    model.load_state_dict(torch.load(CNN3D_WEIGHTS, map_location=device))
    model.eval()

    test_patients = discover_patients(TEST_ROOT)
    patient = test_patients[0]
    dataset = AcdcVolumeDataset([patient], augment=False)
    volume_tensor, label_tensor = dataset[0]
    volume_tensor = volume_tensor.unsqueeze(0).to(device)  # (1, 2, X, Y, Z)
    true_class_index = int(label_tensor.item())
    class_names = [d.value for d in DiagnosisClass]
    print(f"patient: {patient.patient_id}  true class: {class_names[true_class_index]}", flush=True)

    result = grad_cam_3d(model, volume_tensor)
    predicted_class = class_names[result.predicted_class_index]
    print(f"predicted class: {predicted_class}  layer: {result.layer_name}", flush=True)

    ed_channel = volume_tensor.squeeze(0)[0].cpu().numpy()  # (X, Y, Z)
    z_index = ed_channel.shape[2] // 2
    out_path = OUT_DIR / f"cnn3d_gradcam_{patient.patient_id}_z{z_index}.png"
    _save_cnn3d_gradcam_overlay(ed_channel, result.attribution, z_index, out_path)
    print(f"  attribution_mean={float(result.attribution.mean()):.4f} -> {out_path.name}", flush=True)

    return {
        "patient_id": patient.patient_id,
        "true_class": class_names[true_class_index],
        "predicted_class": predicted_class,
        "layer_name": result.layer_name,
        "attribution_mean": float(result.attribution.mean()),
        "attribution_max": float(result.attribution.max()),
        "png_path": str(out_path.relative_to(REPO_ROOT)),
    }


def run_lime_shapley_showcase() -> dict:
    print("=== LIME vs Shapley pedagogical panel (ADR-3) ===", flush=True)
    train_patients = discover_patients(TRAIN_ROOT)
    test_patients = discover_patients(TEST_ROOT)
    class_names = [d.value for d in DiagnosisClass]
    class_labels = set(class_names)

    print(f"computing real background biomarkers from {len(train_patients)} training patients...", flush=True)
    background = real_background_biomarker_features(train_patients)
    training_cases = [
        TrainingCase(features=features, label=patient.diagnosis_class)
        for patient, features in zip(train_patients, background, strict=True)
    ]
    prototypes = fit_nearest_centroid(training_cases, class_labels)
    baseline = prototypes[DiagnosisClass.NORMAL.value]

    explainer = build_lime_explainer(background, class_names)

    patient = test_patients[0]
    features = reference_biomarker_features(patient)
    panel = build_explanation_panel(patient.patient_id, features, prototypes, baseline, explainer, class_names)

    print(f"patient: {panel.patient_id}  predicted class: {panel.predicted_class}", flush=True)
    for method, attributions in panel.method_attributions.items():
        rendered = ", ".join(f"{name}={value:+.3f}" for name, value in attributions.items())
        print(f"  {method}: {rendered}", flush=True)

    return {
        "patient_id": panel.patient_id,
        "predicted_class": panel.predicted_class,
        "method_attributions": panel.method_attributions,
        "note": panel.note,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}", flush=True)

    unet_summary = run_unet_showcase(device)
    cnn3d_summary = run_cnn3d_showcase(device)
    lime_shapley_summary = run_lime_shapley_showcase()

    out_path = OUT_DIR / "explainability_showcase.json"
    out_path.write_text(
        json.dumps(
            {
                "unet_seg_grad_cam": unet_summary,
                "cnn3d_grad_cam": cnn3d_summary,
                "lime_shapley_panel": lime_shapley_summary,
            },
            indent=2,
        )
    )
    print(f"saved to {out_path}", flush=True)


if __name__ == "__main__":
    main()
