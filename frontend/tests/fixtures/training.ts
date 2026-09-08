import type {
  AggregateStructureMetrics,
  ClassificationValidationReport,
  Cnn3dMetrics,
  DispersionSummary,
  ModelEvaluationOut,
  ModelVersionOut,
  NearestCentroidMetrics,
  StructureMetrics,
  UnetMetrics,
} from "../../src/api/training";

const LABELS = ["NORMAL", "DILATED_CARDIOMYOPATHY", "HYPERTROPHIC_CARDIOMYOPATHY"];

function dispersion(mean: number): DispersionSummary {
  return { mean, std: 0.05, median: mean, iqr: 0.08, min: mean - 0.1, max: mean + 0.1, undefined_count: 0 };
}

function structureMetrics(dice: number): StructureMetrics {
  return {
    dice,
    iou: dice - 0.05,
    precision: dice + 0.01,
    recall: dice - 0.01,
    specificity: 0.99,
    volumetric_similarity: 0.95,
    relative_volume_error_percent: 3.2,
    hausdorff_distance_mm: 6.4,
    hausdorff_distance_95_mm: 4.1,
    average_symmetric_surface_distance_mm: 1.2,
    empty_prediction: false,
    empty_target: false,
    connected_components: 1,
  };
}

function aggregateStructureMetrics(dice: number): AggregateStructureMetrics {
  return {
    dice: dispersion(dice),
    iou: dispersion(dice - 0.05),
    precision: dispersion(dice + 0.01),
    recall: dispersion(dice - 0.01),
    specificity: dispersion(0.99),
    volumetric_similarity: dispersion(0.95),
    relative_volume_error_percent: dispersion(3.2),
    hausdorff_distance_mm: dispersion(6.4),
    hausdorff_distance_95_mm: dispersion(4.1),
    average_symmetric_surface_distance_mm: dispersion(1.2),
    empty_prediction_count: 0,
    empty_prediction_percent: 0,
    empty_target_count: 0,
    empty_target_percent: 0,
    connected_components_mean: 1,
  };
}

const STRUCTURES = ["LV", "RV", "MYO"];
const PHASES = ["ED", "ES"];

export const unetMetrics: UnetMetrics = {
  best_val_mean_dice_foreground: 0.87,
  best_epoch: 42,
  total_epochs: 60,
  time_to_best_epoch_s: 1234.5,
  degradation_since_best_epoch: 0.01,
  test: { per_class_dice: [0.9, 0.85, 0.82], mean_dice_foreground: 0.857 },
  detailed_validation: {
    structures: STRUCTURES,
    phases: PHASES,
    patient_count: 2,
    per_patient: {
      "patient-1": {
        ED: {
          structures: { LV: structureMetrics(0.9), RV: structureMetrics(0.85), MYO: structureMetrics(0.82) },
          anatomical_violation: false,
        },
        ES: {
          structures: { LV: structureMetrics(0.88), RV: structureMetrics(0.83), MYO: structureMetrics(0.8) },
          anatomical_violation: false,
        },
      },
    },
    aggregate: {
      LV: { ED: aggregateStructureMetrics(0.9), ES: aggregateStructureMetrics(0.88) },
      RV: { ED: aggregateStructureMetrics(0.85), ES: aggregateStructureMetrics(0.83) },
      MYO: { ED: aggregateStructureMetrics(0.82), ES: aggregateStructureMetrics(0.8) },
    },
    anatomical_violation_rate_percent: { ED: 0, ES: 2.5 },
    bootstrap_ci_95_dice: {
      LV_ED: [0.86, 0.93],
      LV_ES: [0.84, 0.91],
      RV_ED: [0.8, 0.89],
      RV_ES: [0.78, 0.87],
      MYO_ED: [0.77, 0.86],
      MYO_ES: [0.75, 0.84],
    },
  },
  history: [
    { epoch: 1, train_loss: 0.9, epoch_time_s: 20, per_class_dice: [0.5, 0.4, 0.3], mean_dice_foreground: 0.4 },
    { epoch: 2, train_loss: 0.6, epoch_time_s: 20, per_class_dice: [0.7, 0.6, 0.55], mean_dice_foreground: 0.6 },
  ],
  train_patients: ["patient-1", "patient-2"],
  val_patients: ["patient-3"],
  test_patients: ["patient-4", "patient-5"],
};

function makeClassificationValidationReport(labels: string[], accuracy: number): ClassificationValidationReport {
  const n = labels.length;
  const matrix = labels.map((_, i) => labels.map((_, j) => (i === j ? 8 : 1)));
  const perClass = Object.fromEntries(
    labels.map((label) => [label, { precision: 0.8, recall: 0.75, specificity: 0.9, npv: 0.85, f1: 0.77 }]),
  );
  const rocPerClass = Object.fromEntries(
    labels.map((label) => [label, { fpr: [0, 0.2, 1], tpr: [0, 0.8, 1], auc: 0.9 }]),
  );
  const prPerClass = Object.fromEntries(
    labels.map((label) => [label, { precision: [1, 0.8, 0.5], recall: [0, 0.5, 1], average_precision: 0.85 }]),
  );
  const prevalence = Object.fromEntries(labels.map((label) => [label, 1 / n]));
  const perClassBrier = Object.fromEntries(labels.map((label) => [label, 0.1]));

  return {
    labels,
    sample_count: 30,
    confusion_matrix: matrix,
    confusion_matrix_normalized_true: matrix.map((row) => {
      const total = row.reduce((a, b) => a + b, 0);
      return row.map((v) => v / total);
    }),
    confusion_matrix_normalized_predicted: matrix,
    accuracy,
    balanced_accuracy: accuracy - 0.02,
    error_rate: 1 - accuracy,
    per_class: perClass,
    macro: { precision: 0.8, recall: 0.78, f1: 0.79 },
    weighted: { precision: 0.81, recall: 0.79, f1: 0.8 },
    micro: { precision: 0.82, recall: 0.82, f1: 0.82 },
    matthews_correlation_coefficient: 0.7,
    cohens_kappa: 0.68,
    top_2_accuracy: 0.95,
    roc: { per_class: rocPerClass, macro_auc: 0.91, weighted_auc: 0.9, micro: { fpr: [0, 0.2, 1], tpr: [0, 0.85, 1], auc: 0.92 } },
    precision_recall: {
      per_class: prPerClass,
      macro_pr_auc: 0.86,
      micro_pr_auc: 0.87,
      weighted_pr_auc: 0.86,
      prevalence,
    },
    calibration: {
      multiclass_brier_score: 0.12,
      per_class_brier_score: perClassBrier,
      log_loss: 0.4,
      top1_reliability_diagram: {
        bin_confidence: [0.1, 0.5, 0.9],
        bin_accuracy: [0.15, 0.48, 0.86],
        bin_count: [5, 10, 15],
        ece: 0.04,
        mce: 0.09,
        calibration_slope: 0.95,
        calibration_intercept: 0.02,
      },
      high_confidence_error_rate_90: 0.05,
    },
    selective_prediction: {
      risk_coverage_curve: [
        { coverage: 1, accuracy, macro_f1: 0.79 },
        { coverage: 0.8, accuracy: accuracy + 0.05, macro_f1: 0.83 },
        { coverage: 0.5, accuracy: accuracy + 0.1, macro_f1: 0.88 },
      ],
      selective_accuracy_reject_5pct: accuracy + 0.02,
      selective_accuracy_reject_10pct: accuracy + 0.04,
      selective_accuracy_reject_20pct: accuracy + 0.06,
    },
    bootstrap_ci_95: {
      accuracy: [accuracy - 0.05, accuracy + 0.05],
      balanced_accuracy: [accuracy - 0.07, accuracy + 0.03],
      macro_f1: [0.72, 0.85],
    },
  };
}

export const cnn3dMetrics: Cnn3dMetrics = {
  cross_validation: {
    k: 3,
    mean_accuracy: 0.8,
    std_accuracy: 0.03,
    median_accuracy: 0.81,
    iqr_accuracy: 0.04,
    min_accuracy: 0.76,
    max_accuracy: 0.84,
    folds: [
      {
        fold: 1,
        test_patients: ["p1", "p2"],
        accuracy: 0.79,
        training: {
          best_val_accuracy: 0.8,
          best_epoch: 12,
          total_epochs: 20,
          time_to_best_epoch_s: 500,
          degradation_since_best_epoch: 0.01,
          history: [{ epoch: 1, train_loss: 1.1, val_accuracy: 0.4, epoch_time_s: 25 }],
        },
        validation: makeClassificationValidationReport(LABELS, 0.79),
      },
      {
        fold: 2,
        test_patients: ["p3", "p4"],
        accuracy: 0.81,
        training: {
          best_val_accuracy: 0.82,
          best_epoch: 14,
          total_epochs: 20,
          time_to_best_epoch_s: 520,
          degradation_since_best_epoch: 0.0,
          history: [{ epoch: 1, train_loss: 1.0, val_accuracy: 0.45, epoch_time_s: 26 }],
        },
        validation: makeClassificationValidationReport(LABELS, 0.81),
      },
    ],
    out_of_fold_validation: makeClassificationValidationReport(LABELS, 0.8),
  },
  final_model_training: {
    best_val_accuracy: 0.83,
    best_epoch: 15,
    total_epochs: 20,
    time_to_best_epoch_s: 600,
    degradation_since_best_epoch: 0.0,
    history: [
      { epoch: 1, train_loss: 1.1, val_accuracy: 0.4, epoch_time_s: 25 },
      { epoch: 2, train_loss: 0.8, val_accuracy: 0.6, epoch_time_s: 25 },
    ],
  },
  external_test: {
    test_patients: ["p5", "p6", "p7"],
    accuracy: 0.82,
    validation: makeClassificationValidationReport(LABELS, 0.82),
  },
};

export const nearestCentroidMetrics: NearestCentroidMetrics = {
  case_count: 40,
  correct_count: 30,
  per_class_accuracy: { NORMAL: 0.85, DILATED_CARDIOMYOPATHY: 0.7, HYPERTROPHIC_CARDIOMYOPATHY: 0.65 },
};

export function makeModelVersion(overrides: Partial<ModelVersionOut> = {}): ModelVersionOut {
  return {
    id: "model-version-1",
    training_run_id: "run-1",
    name: "cardiac-classifier",
    mlflow_run_id: "mlflow-1",
    mlflow_model_uri: "runs:/mlflow-1/model",
    status: "ACTIVE",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export function makeEvaluation(metrics: Record<string, unknown>, overrides: Partial<ModelEvaluationOut> = {}): ModelEvaluationOut {
  return {
    id: "eval-1",
    model_version_id: "model-version-1",
    split: "TEST",
    accuracy: 0.8,
    metrics,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}
