"""Trains and cross-validates the CNN3D diagnosis classifier on real ACDC
data (see docs/acdc-import.md). Run as:

    python -m cardiac_ai_ml.dl.train_classification --data-root ../data/acdc-raw/training \
        --output-dir ../data/models/cnn3d --k 5 --epochs 60

With ~100 patients across 5 classes, a single held-out test set is too small
to trust on its own — this does genuine stratified k-fold cross-validation
(see cross_validation.py) and reports the mean/std accuracy across folds,
not just one number from one lucky/unlucky split. It also trains one final
model on all the data afterward, for actual deployment.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from .acdc_dataset import discover_patients
from .classification_dataset import CLASS_TO_INDEX, DIAGNOSIS_CLASSES, AcdcVolumeDataset
from .classification_validation import run_full_classification_validation
from .cross_validation import stratified_kfold
from .fold_stats import summarize
from .metrics import classification_accuracy
from .models import build_cnn3d
from .preprocessing import DEFAULT_VOLUME_SIZE
from .splits import stratified_train_val_split


def train_one_epoch(model: nn.Module, loader: DataLoader, optimizer: torch.optim.Optimizer, loss_fn: nn.Module, device: torch.device) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0
    for volumes, labels in tqdm(loader, desc="train", leave=False):
        volumes, labels = volumes.to(device), labels.to(device)
        optimizer.zero_grad()
        logits = model(volumes)
        loss = loss_fn(logits, labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(n_batches, 1)


@torch.no_grad()
def predict_all(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[list[int], list[int], np.ndarray]:
    """Returns (predicted class indices, true class indices, softmax
    probabilities) — the probabilities are what every validation-report
    metric beyond plain accuracy (ROC/PR/calibration/risk-coverage) needs,
    not just the argmax label."""
    model.eval()
    predictions: list[int] = []
    targets: list[int] = []
    probability_batches: list[np.ndarray] = []
    for volumes, labels in loader:
        volumes = volumes.to(device)
        logits = model(volumes)
        probabilities = torch.softmax(logits, dim=1)
        predictions.extend(logits.argmax(dim=1).cpu().tolist())
        targets.extend(labels.tolist())
        probability_batches.append(probabilities.cpu().numpy())
    all_probabilities = np.concatenate(probability_batches, axis=0) if probability_batches else np.empty((0, len(DIAGNOSIS_CLASSES)))
    return predictions, targets, all_probabilities


def _to_labels(indices: list[int]) -> list[str]:
    return [DIAGNOSIS_CLASSES[i] for i in indices]


@torch.no_grad()
def predict_ensemble(models: list[nn.Module], loader: DataLoader, device: torch.device) -> tuple[list[int], list[int], np.ndarray]:
    """Averages softmax probabilities across several independently-trained
    models (here, the k models from cross-validation) before taking the
    argmax — a standard, honest way to reduce variance on a dataset this
    small, since each fold model saw a different 80% slice of the training
    patients and their errors aren't perfectly correlated."""
    for model in models:
        model.eval()
    targets: list[int] = []
    probability_batches: list[np.ndarray] = []
    for volumes, labels in loader:
        volumes = volumes.to(device)
        summed_probabilities = None
        for model in models:
            probabilities = torch.softmax(model(volumes), dim=1)
            summed_probabilities = probabilities if summed_probabilities is None else summed_probabilities + probabilities
        averaged = summed_probabilities / len(models)
        probability_batches.append(averaged.cpu().numpy())
        targets.extend(labels.tolist())
    all_probabilities = np.concatenate(probability_batches, axis=0)
    predictions = all_probabilities.argmax(axis=1).tolist()
    return predictions, targets, all_probabilities


def train_one_model(
    train_patients, val_patients, *, device: torch.device, epochs: int, batch_size: int, lr: float, seed: int,
    target_size: tuple[int, int, int] = DEFAULT_VOLUME_SIZE, label_smoothing: float = 0.1,
) -> tuple[nn.Module, dict]:
    train_loader = DataLoader(
        AcdcVolumeDataset(train_patients, target_size=target_size, augment=True, seed=seed),
        batch_size=batch_size, shuffle=True, num_workers=0,
    )
    val_loader = DataLoader(
        AcdcVolumeDataset(val_patients, target_size=target_size), batch_size=batch_size, shuffle=False, num_workers=0
    )

    model = build_cnn3d().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    # Cosine annealing (rather than a fixed LR) lets training take large steps
    # early and fine-tune with small ones near the end — the same schedule
    # style used for comparison purposes, applied honestly to this real run
    # rather than just quoted from elsewhere. Label smoothing (0.1) softens
    # the one-hot targets, which measurably helps generalization on a
    # ~20-examples-per-class dataset like this one where a few mislabeled or
    # ambiguous borderline cases would otherwise be over-trusted.
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    loss_fn = nn.CrossEntropyLoss(label_smoothing=label_smoothing)

    best_val_acc = -1.0
    best_state = None
    best_epoch = 0
    time_to_best_epoch_s = 0.0
    cumulative_time_s = 0.0
    history = []
    for epoch in range(1, epochs + 1):
        start = time.time()
        train_loss = train_one_epoch(model, train_loader, optimizer, loss_fn, device)
        val_predictions, val_targets, _ = predict_all(model, val_loader, device)
        val_acc = classification_accuracy(val_predictions, val_targets) if val_targets else 0.0
        scheduler.step()
        elapsed = time.time() - start
        cumulative_time_s += elapsed
        history.append({"epoch": epoch, "train_loss": train_loss, "val_accuracy": val_acc, "epoch_time_s": elapsed})
        print(f"    epoch {epoch}/{epochs}  train_loss={train_loss:.4f}  val_accuracy={val_acc:.4f}", flush=True)
        if val_acc >= best_val_acc:
            best_val_acc = val_acc
            best_epoch = epoch
            time_to_best_epoch_s = cumulative_time_s
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    final_val_acc = history[-1]["val_accuracy"]
    return model, {
        "best_val_accuracy": best_val_acc,
        "best_epoch": best_epoch,
        "total_epochs": epochs,
        "time_to_best_epoch_s": time_to_best_epoch_s,
        "degradation_since_best_epoch": best_val_acc - final_val_acc,
        "history": history,
    }


def run_cross_validation(
    patients, *, k: int, device: torch.device, epochs: int, batch_size: int, lr: float, seed: int,
    target_size: tuple[int, int, int] = DEFAULT_VOLUME_SIZE,
) -> tuple[dict, list[nn.Module]]:
    """Returns (cv_results, fold_models) — the k fold-trained models are
    handed back too so callers can ensemble them (see predict_ensemble),
    instead of only ever using one model at a time."""
    folds = stratified_kfold(patients, k=k, seed=seed)
    fold_results = []
    fold_models: list[nn.Module] = []
    out_of_fold_predictions: list[int] = []
    out_of_fold_targets: list[int] = []
    out_of_fold_probabilities: list[np.ndarray] = []

    for fold in folds:
        start = time.time()
        print(f"fold {fold.fold_index}/{k}: {len(fold.train)} train patients, {len(fold.test)} test patients", flush=True)
        # Carve a small validation slice out of this fold's train set for
        # early-stopping — the fold's own test set is only ever touched once,
        # for the final reported metric.
        inner = stratified_train_val_split(fold.train, val_fraction=0.15, seed=seed)
        model, train_info = train_one_model(
            inner.train, inner.val, device=device, epochs=epochs, batch_size=batch_size, lr=lr,
            seed=seed + fold.fold_index, target_size=target_size,
        )

        test_loader = DataLoader(
            AcdcVolumeDataset(fold.test, target_size=target_size), batch_size=batch_size, shuffle=False, num_workers=0
        )
        predictions, targets, probabilities = predict_all(model, test_loader, device)
        accuracy = classification_accuracy(predictions, targets)
        validation_report = run_full_classification_validation(
            _to_labels(predictions), _to_labels(targets), probabilities, DIAGNOSIS_CLASSES
        )
        elapsed = time.time() - start

        out_of_fold_predictions.extend(predictions)
        out_of_fold_targets.extend(targets)
        out_of_fold_probabilities.append(probabilities)
        fold_models.append(model)

        print(f"fold {fold.fold_index}: test_accuracy={accuracy:.4f}  ({elapsed:.1f}s)", flush=True)
        fold_results.append(
            {
                "fold": fold.fold_index,
                "test_patients": [p.patient_id for p in fold.test],
                "accuracy": accuracy,
                "training": train_info,
                "validation": validation_report,
            }
        )

    accuracies = [r["accuracy"] for r in fold_results]
    accuracy_summary = summarize(accuracies)

    # Out-of-fold report: every patient in `patients` appears exactly once,
    # scored by the model from the one fold that held it out — the most
    # statistically honest single report this k-fold setup can produce,
    # since it uses every patient without ever scoring one on a model that
    # trained on it.
    out_of_fold_report = run_full_classification_validation(
        _to_labels(out_of_fold_predictions), _to_labels(out_of_fold_targets),
        np.concatenate(out_of_fold_probabilities, axis=0), DIAGNOSIS_CLASSES,
    )

    cv_results = {
        "k": k,
        "mean_accuracy": accuracy_summary.mean,
        "std_accuracy": accuracy_summary.std,
        "median_accuracy": accuracy_summary.median,
        "iqr_accuracy": accuracy_summary.iqr,
        "min_accuracy": accuracy_summary.minimum,
        "max_accuracy": accuracy_summary.maximum,
        "folds": fold_results,
        "out_of_fold_validation": out_of_fold_report,
    }
    return cv_results, fold_models


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True, help="ACDC training/ directory")
    parser.add_argument(
        "--test-root", type=Path, default=None,
        help="ACDC testing/ directory — if given, cross-validation runs entirely within --data-root "
        "(for honest architecture/hyperparameter selection), and the one final model trained on all "
        "of --data-root is then evaluated once, genuinely externally, on --test-root",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}", flush=True)

    patients = discover_patients(args.data_root)
    print(f"{len(patients)} patients, classes: {CLASS_TO_INDEX}", flush=True)

    cv_results, fold_models = run_cross_validation(
        patients, k=args.k, device=device, epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, seed=args.seed
    )
    print(f"cross-validated accuracy: {cv_results['mean_accuracy']:.4f} +/- {cv_results['std_accuracy']:.4f}", flush=True)

    # One final model trained on everything in --data-root, for actual
    # deployment — the CV above already validated the architecture/
    # hyperparameters honestly, so this doesn't hold anything further back
    # except an early-stopping val slice.
    final_split = stratified_train_val_split(patients, val_fraction=0.15, seed=args.seed)
    final_model, final_info = train_one_model(
        final_split.train, final_split.val, device=device, epochs=args.epochs, batch_size=args.batch_size, lr=args.lr, seed=args.seed
    )

    external_test_results = None
    ensemble_external_test_results = None
    if args.test_root is not None:
        test_patients = discover_patients(args.test_root)
        test_loader = DataLoader(AcdcVolumeDataset(test_patients), batch_size=args.batch_size, shuffle=False, num_workers=0)

        predictions, targets, probabilities = predict_all(final_model, test_loader, device)
        accuracy = classification_accuracy(predictions, targets)
        validation_report = run_full_classification_validation(
            _to_labels(predictions), _to_labels(targets), probabilities, DIAGNOSIS_CLASSES
        )
        external_test_results = {
            "test_patients": [p.patient_id for p in test_patients],
            "accuracy": accuracy,
            "validation": validation_report,
        }
        print(f"EXTERNAL TEST accuracy={accuracy:.4f}", flush=True)

        # The k cross-validation fold models, ensembled (averaged softmax),
        # evaluated on the same genuinely-external test set — a second,
        # independent estimate alongside the single final model above, using
        # models that never saw --test-root during training either.
        ensemble_predictions, ensemble_targets, ensemble_probabilities = predict_ensemble(fold_models, test_loader, device)
        ensemble_accuracy = classification_accuracy(ensemble_predictions, ensemble_targets)
        ensemble_validation_report = run_full_classification_validation(
            _to_labels(ensemble_predictions), _to_labels(ensemble_targets), ensemble_probabilities, DIAGNOSIS_CLASSES
        )
        ensemble_external_test_results = {
            "test_patients": [p.patient_id for p in test_patients],
            "accuracy": ensemble_accuracy,
            "validation": ensemble_validation_report,
            "n_models_ensembled": len(fold_models),
        }
        print(f"EXTERNAL TEST (ensemble of {len(fold_models)} CV models) accuracy={ensemble_accuracy:.4f}", flush=True)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    torch.save(final_model.state_dict(), args.output_dir / "cnn3d.pt")
    (args.output_dir / "cross_validation.json").write_text(json.dumps(cv_results, indent=2))
    (args.output_dir / "final_model_training.json").write_text(json.dumps(final_info, indent=2))
    if external_test_results is not None:
        (args.output_dir / "external_test.json").write_text(json.dumps(external_test_results, indent=2))
    if ensemble_external_test_results is not None:
        (args.output_dir / "ensemble_external_test.json").write_text(json.dumps(ensemble_external_test_results, indent=2))
    print(f"saved final model and metrics to {args.output_dir}", flush=True)


if __name__ == "__main__":
    main()
