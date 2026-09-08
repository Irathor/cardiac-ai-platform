"""Trains the 2D U-Net on real ACDC data (see docs/acdc-import.md). Run as:

    python -m cardiac_ai_ml.dl.train_segmentation --data-root ../data/acdc-raw/training \
        --output ../data/models/unet2d.pt --epochs 50

Needs the `dl` extra (`pip install torch --index-url https://download.pytorch.org/whl/cu126`
then `pip install -e ".[dl]"` — see pyproject.toml) and a real ACDC training/ folder; refuses
to run against synthetic/fabricated data, per this project's "never fabricate a result" rule.
"""
import argparse
import json
import time
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader
from tqdm import tqdm

from .acdc_dataset import discover_patients
from .metrics import dice_score_per_class, mean_dice_excluding_background
from .models import NUM_SEGMENTATION_CLASSES, build_unet2d
from .segmentation_dataset import AcdcSliceDataset
from .segmentation_validation import run_full_segmentation_validation
from .splits import stratified_patient_split, stratified_train_val_split


def train_one_epoch(model: nn.Module, loader: DataLoader, optimizer: torch.optim.Optimizer, loss_fn: nn.Module, device: torch.device) -> float:
    model.train()
    total_loss = 0.0
    n_batches = 0
    for images, masks in tqdm(loader, desc="train", leave=False):
        images, masks = images.to(device), masks.to(device)
        optimizer.zero_grad()
        logits = model(images)
        loss = loss_fn(logits, masks)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
        n_batches += 1
    return total_loss / max(n_batches, 1)


@torch.no_grad()
def evaluate(model: nn.Module, loader: DataLoader, device: torch.device, num_classes: int = NUM_SEGMENTATION_CLASSES) -> dict:
    model.eval()
    per_class_totals = [0.0] * num_classes
    n_batches = 0
    for images, masks in loader:
        images, masks = images.to(device), masks.to(device)
        logits = model(images)
        predictions = logits.argmax(dim=1)
        for i in range(images.shape[0]):
            scores = dice_score_per_class(predictions[i], masks[i], num_classes)
            for c in range(num_classes):
                per_class_totals[c] += scores[c]
            n_batches += 1
    per_class_dice = [t / max(n_batches, 1) for t in per_class_totals]
    return {
        "per_class_dice": per_class_dice,
        "mean_dice_foreground": mean_dice_excluding_background(per_class_dice),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True, help="ACDC training/ directory")
    parser.add_argument(
        "--test-root", type=Path, default=None,
        help="ACDC testing/ directory, used as a genuine external test set never seen during "
        "model selection (if omitted, a test split is instead carved out of --data-root)",
    )
    parser.add_argument("--output", type=Path, required=True, help="where to save the trained model (.pt)")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--val-fraction", type=float, default=0.15)
    parser.add_argument("--test-fraction", type=float, default=0.15, help="ignored when --test-root is given")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}", flush=True)

    patients = discover_patients(args.data_root)
    if args.test_root is not None:
        train_val = stratified_train_val_split(patients, val_fraction=args.val_fraction, seed=args.seed)
        test_patients = discover_patients(args.test_root)
        train_patients, val_patients = train_val.train, train_val.val
    else:
        splits = stratified_patient_split(
            patients, val_fraction=args.val_fraction, test_fraction=args.test_fraction, seed=args.seed
        )
        train_patients, val_patients, test_patients = splits.train, splits.val, splits.test
    print(f"patients: {len(train_patients)} train / {len(val_patients)} val / {len(test_patients)} test", flush=True)

    train_loader = DataLoader(AcdcSliceDataset(train_patients), batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(AcdcSliceDataset(val_patients), batch_size=args.batch_size, shuffle=False, num_workers=0)
    test_loader = DataLoader(AcdcSliceDataset(test_patients), batch_size=args.batch_size, shuffle=False, num_workers=0)
    print(
        f"slices: {len(train_loader.dataset)} train / {len(val_loader.dataset)} val / {len(test_loader.dataset)} test "
        f"({len(train_loader)} train batches/epoch)",
        flush=True,
    )

    model = build_unet2d().to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = nn.CrossEntropyLoss()

    best_val_dice = -1.0
    best_state = None
    best_epoch = 0
    time_to_best_epoch_s = 0.0
    cumulative_time_s = 0.0
    history = []

    for epoch in range(1, args.epochs + 1):
        start = time.time()
        train_loss = train_one_epoch(model, train_loader, optimizer, loss_fn, device)
        val_metrics = evaluate(model, val_loader, device)
        elapsed = time.time() - start
        cumulative_time_s += elapsed
        print(
            f"epoch {epoch}/{args.epochs}  train_loss={train_loss:.4f}  "
            f"val_mean_dice_fg={val_metrics['mean_dice_foreground']:.4f}  ({elapsed:.1f}s)",
            flush=True,
        )
        history.append({"epoch": epoch, "train_loss": train_loss, "epoch_time_s": elapsed, **val_metrics})

        if val_metrics["mean_dice_foreground"] > best_val_dice:
            best_val_dice = val_metrics["mean_dice_foreground"]
            best_epoch = epoch
            time_to_best_epoch_s = cumulative_time_s
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

    model.load_state_dict(best_state)
    test_metrics = evaluate(model, test_loader, device)
    print(f"TEST mean_dice_foreground={test_metrics['mean_dice_foreground']:.4f}")
    print(f"TEST per_class_dice={test_metrics['per_class_dice']}")

    final_val_dice = history[-1]["mean_dice_foreground"]
    print("running detailed per-structure/per-phase validation on the test set...", flush=True)
    detailed_validation = run_full_segmentation_validation(model, test_patients, device)
    print(f"detailed validation done — anatomical_violation_rate={detailed_validation['anatomical_violation_rate_percent']}", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, args.output)
    metrics_path = args.output.with_suffix(".metrics.json")
    metrics_path.write_text(
        json.dumps(
            {
                "best_val_mean_dice_foreground": best_val_dice,
                "best_epoch": best_epoch,
                "total_epochs": args.epochs,
                "time_to_best_epoch_s": time_to_best_epoch_s,
                "degradation_since_best_epoch": best_val_dice - final_val_dice,
                "test": test_metrics,
                "detailed_validation": detailed_validation,
                "history": history,
                "train_patients": [p.patient_id for p in train_patients],
                "val_patients": [p.patient_id for p in val_patients],
                "test_patients": [p.patient_id for p in test_patients],
            },
            indent=2,
        )
    )
    print(f"saved model to {args.output}")
    print(f"saved metrics to {metrics_path}")


if __name__ == "__main__":
    main()
