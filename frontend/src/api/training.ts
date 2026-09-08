import { apiGetAuthed, apiPostAuthed } from "./client";

export type TrainingModelType = "NEAREST_CENTROID" | "UNET_SEGMENTATION" | "CNN3D_CLASSIFICATION";

export type TrainingRunStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED" | "CANCELLED";

export interface TrainingRunOut {
  id: string;
  dataset_version_id: string | null;
  model_type: TrainingModelType;
  status: TrainingRunStatus;
  mlflow_run_id: string | null;
  metrics: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

/** "cardiac-classifier" (nearest-centroid) | "cardiac-segmentation-unet" | "cardiac-classifier-cnn3d". */
export interface ModelVersionOut {
  id: string;
  training_run_id: string;
  name: string;
  mlflow_run_id: string;
  mlflow_model_uri: string;
  status: string;
  created_at: string;
}

export interface ModelEvaluationOut {
  id: string;
  model_version_id: string;
  split: string;
  accuracy: number | null;
  metrics: Record<string, unknown>;
  created_at: string;
}

/** metrics shape for name === "cardiac-classifier" (nearest-centroid, unchanged legacy behavior). */
export interface NearestCentroidMetrics {
  case_count: number;
  correct_count: number;
  per_class_accuracy: Record<string, number>;
}

// --- Segmentation (U-Net) metrics — name === "cardiac-segmentation-unet" ---

export interface StructureMetrics {
  dice: number;
  iou: number;
  precision: number;
  recall: number;
  specificity: number;
  volumetric_similarity: number;
  relative_volume_error_percent: number | null;
  hausdorff_distance_mm: number | null;
  hausdorff_distance_95_mm: number | null;
  average_symmetric_surface_distance_mm: number | null;
  empty_prediction: boolean;
  empty_target: boolean;
  connected_components: number;
}

export interface DispersionSummary {
  mean: number;
  std: number;
  median: number;
  iqr: number;
  min: number;
  max: number;
  undefined_count: number;
}

export interface AggregateStructureMetrics {
  dice: DispersionSummary;
  iou: DispersionSummary;
  precision: DispersionSummary;
  recall: DispersionSummary;
  specificity: DispersionSummary;
  volumetric_similarity: DispersionSummary;
  relative_volume_error_percent: DispersionSummary;
  hausdorff_distance_mm: DispersionSummary;
  hausdorff_distance_95_mm: DispersionSummary;
  average_symmetric_surface_distance_mm: DispersionSummary;
  empty_prediction_count: number;
  empty_prediction_percent: number;
  empty_target_count: number;
  empty_target_percent: number;
  connected_components_mean: number;
}

export interface UnetMetrics {
  best_val_mean_dice_foreground: number;
  best_epoch: number;
  total_epochs: number;
  time_to_best_epoch_s: number;
  degradation_since_best_epoch: number;
  test: { per_class_dice: number[]; mean_dice_foreground: number };
  detailed_validation: {
    structures: string[];
    phases: string[];
    patient_count: number;
    per_patient: Record<string, Record<string, { structures: Record<string, StructureMetrics>; anatomical_violation: boolean }>>;
    aggregate: Record<string, Record<string, AggregateStructureMetrics>>;
    anatomical_violation_rate_percent: Record<string, number>;
    bootstrap_ci_95_dice: Record<string, [number, number]>;
  };
  history: Array<{ epoch: number; train_loss: number; epoch_time_s: number; per_class_dice: number[]; mean_dice_foreground: number }>;
  train_patients: string[];
  val_patients: string[];
  test_patients: string[];
}

// --- Classification (CNN3D) metrics — name === "cardiac-classifier-cnn3d" ---

export interface ClassificationValidationReport {
  labels: string[];
  sample_count: number;
  confusion_matrix: number[][];
  confusion_matrix_normalized_true: number[][];
  confusion_matrix_normalized_predicted: number[][];
  accuracy: number;
  balanced_accuracy: number;
  error_rate: number;
  per_class: Record<string, { precision: number; recall: number; specificity: number; npv: number; f1: number }>;
  macro: { precision: number; recall: number; f1: number };
  weighted: { precision: number; recall: number; f1: number };
  micro: { precision: number; recall: number; f1: number };
  matthews_correlation_coefficient: number;
  cohens_kappa: number;
  top_2_accuracy: number | null;
  roc: {
    per_class: Record<string, { fpr: number[]; tpr: number[]; auc: number }>;
    macro_auc: number | null;
    weighted_auc: number | null;
    micro: { fpr: number[]; tpr: number[]; auc: number };
  };
  precision_recall: {
    per_class: Record<string, { precision: number[]; recall: number[]; average_precision: number }>;
    macro_pr_auc: number;
    micro_pr_auc: number;
    weighted_pr_auc: number;
    prevalence: Record<string, number>;
  };
  calibration: {
    multiclass_brier_score: number;
    per_class_brier_score: Record<string, number>;
    log_loss: number;
    top1_reliability_diagram: {
      bin_confidence: number[];
      bin_accuracy: number[];
      bin_count: number[];
      ece: number;
      mce: number;
      calibration_slope: number;
      calibration_intercept: number;
    };
    high_confidence_error_rate_90: number;
  };
  selective_prediction: {
    risk_coverage_curve: Array<{ coverage: number; accuracy: number; macro_f1: number }>;
    selective_accuracy_reject_5pct: number;
    selective_accuracy_reject_10pct: number;
    selective_accuracy_reject_20pct: number;
  };
  bootstrap_ci_95: { accuracy: [number, number]; balanced_accuracy: [number, number]; macro_f1: [number, number] };
}

export interface FinalModelTraining {
  best_val_accuracy: number;
  best_epoch: number;
  total_epochs: number;
  time_to_best_epoch_s: number;
  degradation_since_best_epoch: number;
  history: Array<{ epoch: number; train_loss: number; val_accuracy: number; epoch_time_s: number }>;
}

export interface CrossValidationResult {
  k: number;
  mean_accuracy: number;
  std_accuracy: number;
  median_accuracy: number;
  iqr_accuracy: number;
  min_accuracy: number;
  max_accuracy: number;
  folds: Array<{ fold: number; test_patients: string[]; accuracy: number; training: FinalModelTraining; validation: ClassificationValidationReport }>;
  out_of_fold_validation: ClassificationValidationReport;
}

export interface ExternalTestResult {
  test_patients: string[];
  accuracy: number;
  validation: ClassificationValidationReport;
}

export interface Cnn3dMetrics {
  cross_validation: CrossValidationResult;
  final_model_training: FinalModelTraining;
  external_test: ExternalTestResult;
}

/** Fixed label order used by the CNN3D classifier — the source of truth for a
 * given report is always its own `labels` field, this is only a reference. */
export const CNN3D_CLASS_LABELS = [
  "NORMAL",
  "DILATED_CARDIOMYOPATHY",
  "HYPERTROPHIC_CARDIOMYOPATHY",
  "MYOCARDIAL_INFARCTION",
  "ABNORMAL_RIGHT_VENTRICLE",
] as const;

export const MODEL_NAME_NEAREST_CENTROID = "cardiac-classifier";
export const MODEL_NAME_UNET = "cardiac-segmentation-unet";
export const MODEL_NAME_CNN3D = "cardiac-classifier-cnn3d";

export function requestTrainingRun(
  datasetId: string,
  versionId: string,
  modelType: TrainingModelType,
  token: string,
): Promise<TrainingRunOut> {
  return apiPostAuthed(
    `/datasets/${datasetId}/versions/${versionId}/training-runs`,
    { model_type: modelType },
    token,
  );
}

export function getTrainingRun(id: string, token: string): Promise<TrainingRunOut> {
  return apiGetAuthed(`/training-runs/${id}`, token);
}

export function listTrainingRunsForVersion(
  datasetId: string,
  versionId: string,
  token: string,
): Promise<TrainingRunOut[]> {
  return apiGetAuthed(`/datasets/${datasetId}/versions/${versionId}/training-runs`, token);
}

/** Preferred history source for the page — unlike listTrainingRunsForVersion,
 * it isn't scoped to one dataset version so it covers all model types. */
export function listModelVersions(token: string): Promise<ModelVersionOut[]> {
  return apiGetAuthed("/model-versions", token);
}

export function getModelVersion(id: string, token: string): Promise<ModelVersionOut> {
  return apiGetAuthed(`/model-versions/${id}`, token);
}

export function listModelEvaluations(modelVersionId: string, token: string): Promise<ModelEvaluationOut[]> {
  return apiGetAuthed(`/model-versions/${modelVersionId}/evaluations`, token);
}
