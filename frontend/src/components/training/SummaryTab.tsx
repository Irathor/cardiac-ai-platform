import { Card, CardContent, Grid, Typography } from "@mui/material";

import {
  type Cnn3dMetrics,
  type ModelEvaluationOut,
  type ModelVersionOut,
  type NearestCentroidMetrics,
  type TrainingRunOut,
  type UnetMetrics,
  MODEL_NAME_CNN3D,
  MODEL_NAME_UNET,
} from "../../api/training";
import { fmtNumber, fmtPercent, NOT_APPLICABLE, NOT_AVAILABLE } from "./format";

interface SummaryTabProps {
  modelVersion: ModelVersionOut;
  evaluation: ModelEvaluationOut;
  runsHistory: TrainingRunOut[];
}

interface StatItem {
  label: string;
  value: string;
}

function meanOfAggregate(unet: UnetMetrics, field: "hausdorff_distance_95_mm"): string {
  const values: number[] = [];
  for (const byPhase of Object.values(unet.detailed_validation.aggregate)) {
    for (const summary of Object.values(byPhase)) {
      const v = summary[field]?.mean;
      if (typeof v === "number" && !Number.isNaN(v)) values.push(v);
    }
  }
  if (values.length === 0) return NOT_AVAILABLE;
  return (values.reduce((a, b) => a + b, 0) / values.length).toFixed(2);
}

function failureRate(runs: TrainingRunOut[]): string {
  if (runs.length === 0) return NOT_AVAILABLE;
  const failed = runs.filter((r) => r.status === "FAILED").length;
  return `${((failed / runs.length) * 100).toFixed(1)}% (${failed}/${runs.length})`;
}

function buildStats(modelVersion: ModelVersionOut, evaluation: ModelEvaluationOut, runsHistory: TrainingRunOut[]): StatItem[] {
  const maeLvef: StatItem = { label: "MAE LVEF", value: NOT_AVAILABLE }; // not computed by any model type yet
  const failure: StatItem = { label: "Failure rate", value: failureRate(runsHistory) };

  if (modelVersion.name === MODEL_NAME_UNET) {
    const unet = evaluation.metrics as unknown as UnetMetrics;
    return [
      { label: "Mean Dice (test)", value: fmtNumber(unet.test?.mean_dice_foreground) },
      { label: "Mean Dice (best val)", value: fmtNumber(unet.best_val_mean_dice_foreground) },
      { label: "Mean HD95 (mm)", value: meanOfAggregate(unet, "hausdorff_distance_95_mm") },
      { label: "Macro F1", value: NOT_APPLICABLE },
      { label: "Balanced accuracy", value: NOT_APPLICABLE },
      { label: "Macro AUC", value: NOT_APPLICABLE },
      { label: "Brier score", value: NOT_APPLICABLE },
      maeLvef,
      failure,
      { label: "Patients (train/val/test)", value: `${unet.train_patients.length}/${unet.val_patients.length}/${unet.test_patients.length}` },
    ];
  }

  if (modelVersion.name === MODEL_NAME_CNN3D) {
    const cnn3d = evaluation.metrics as unknown as Cnn3dMetrics;
    const report = cnn3d.external_test.validation;
    return [
      { label: "Macro F1", value: fmtNumber(report.macro.f1) },
      { label: "Balanced accuracy", value: fmtPercent(report.balanced_accuracy) },
      { label: "Macro AUC", value: fmtNumber(report.roc.macro_auc) },
      { label: "Brier score", value: fmtNumber(report.calibration.multiclass_brier_score) },
      { label: "Mean Dice", value: NOT_APPLICABLE },
      { label: "Mean HD95 (mm)", value: NOT_APPLICABLE },
      maeLvef,
      failure,
      { label: "Test patients", value: String(cnn3d.external_test.test_patients.length) },
      { label: "Cross-validation folds", value: String(cnn3d.cross_validation.k) },
    ];
  }

  // NEAREST_CENTROID — simple legacy metrics, most rich-report fields don't apply.
  const nc = evaluation.metrics as unknown as NearestCentroidMetrics;
  const accuracy = nc.case_count > 0 ? nc.correct_count / nc.case_count : null;
  return [
    { label: "Accuracy", value: fmtPercent(accuracy) },
    { label: "Macro F1", value: NOT_APPLICABLE },
    { label: "Balanced accuracy", value: NOT_APPLICABLE },
    { label: "Macro AUC", value: NOT_APPLICABLE },
    { label: "Brier score", value: NOT_APPLICABLE },
    { label: "Mean Dice", value: NOT_APPLICABLE },
    { label: "Mean HD95 (mm)", value: NOT_APPLICABLE },
    maeLvef,
    failure,
    { label: "Cases evaluated", value: String(nc.case_count) },
  ];
}

export function SummaryTab({ modelVersion, evaluation, runsHistory }: SummaryTabProps) {
  const stats = buildStats(modelVersion, evaluation, runsHistory);

  return (
    <Grid container spacing={2}>
      {stats.map((stat) => (
        <Grid item xs={6} sm={4} md={3} key={stat.label}>
          <Card
            variant="outlined"
            sx={{ transition: "transform 150ms ease, border-color 150ms ease", "&:hover": { transform: "translateY(-2px)", borderColor: "primary.main" } }}
          >
            <CardContent>
              <Typography variant="body2" color="text.secondary">
                {stat.label}
              </Typography>
              <Typography variant="h6" color="primary.light">
                {stat.value}
              </Typography>
            </CardContent>
          </Card>
        </Grid>
      ))}
    </Grid>
  );
}
