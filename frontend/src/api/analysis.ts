import { apiGetAuthed, apiGetBlobAuthed, apiPostAuthed } from "./client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

/** One row of EPIC-12's indirect biomarker-consistency signal — see
 * `BiomarkerConsistency`'s docstring for what it is (and isn't). */
export interface BiomarkerFeatureConsistency {
  feature: string;
  derived_value: number;
  expected_value_for_predicted_class: number;
  scaled_deviation: number;
  consistent: boolean;
}

/**
 * EPIC-12's indirect consistency signal between U-Net-derived biomarkers and
 * the nearest-centroid prototypes for the class CNN3D predicted. This is
 * NOT an exact attribution of the CNN3D model (that's what `feature_attributions`
 * would be, and it's always `null` for CNN3D) — it's a comparison against a
 * different classifier's prototypes, computed after the fact.
 */
export interface BiomarkerConsistency {
  predicted_class: string;
  reference_source: string;
  per_feature: BiomarkerFeatureConsistency[];
  distance_to_each_class: Record<string, number>;
}

export interface AIAnalysis {
  id: string;
  imaging_study_id: string;
  status: "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
  model_version: string;
  features: Record<string, number> | null;
  predicted_class: string | null;
  probabilities: Record<string, number> | null;
  confidence: number | null;
  feature_attributions: Record<string, number> | null;
  error_message: string | null;
  // EPIC-3: whether GET /analyses/{id}/gradcam has an attribution map to
  // serve, and the honest reason when it doesn't (see backend
  // AIAnalysisOut.gradcam_available for the full rationale).
  gradcam_available: boolean;
  gradcam_error: string | null;
  // EPIC-12: see `BiomarkerConsistency` above.
  biomarker_consistency: BiomarkerConsistency | null;
  biomarker_consistency_error: string | null;
  // EPIC-18: whether a cached LLM explanation already exists, and the
  // honest reason when the last generation attempt failed. See
  // `fetchOrGenerateLlmExplanation` for the actual text.
  llm_explanation_available: boolean;
  llm_explanation_error: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface LlmExplanation {
  explanation: string | null;
  error: string | null;
}

export async function requestAnalysis(studyId: string, token: string): Promise<AIAnalysis> {
  const response = await fetch(`${API_BASE_URL}/studies/${studyId}/analyses`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`Requesting analysis failed with ${response.status}`);
  }
  return response.json() as Promise<AIAnalysis>;
}

export function fetchAnalysis(analysisId: string, token: string): Promise<AIAnalysis> {
  return apiGetAuthed(`/analyses/${analysisId}`, token);
}

/** Raw `.npy` bytes for a Grad-CAM attribution map — see `lib/npy.ts` for
 * how the frontend parses them. Same pattern as `fetchSegmentationFile` in
 * `api/imaging.ts`: only call this when `AIAnalysis.gradcam_available` is
 * `true`, otherwise the server 404s with `gradcam_error` as its detail. */
export function fetchGradcamAttribution(analysisId: string, token: string): Promise<Blob> {
  return apiGetBlobAuthed(`/analyses/${analysisId}/gradcam`, token);
}

/** EPIC-18: returns the cached explanation if one exists (unless `force`),
 * otherwise generates one for real via the local Ollama model. Always
 * resolves with either `explanation` or `error` set — a generation failure
 * (e.g. Ollama not running) is not thrown, it's the honest `error` field,
 * same pattern as `gradcam_error`/`biomarker_consistency_error`. */
export function fetchOrGenerateLlmExplanation(
  analysisId: string,
  token: string,
  force = false,
): Promise<LlmExplanation> {
  return apiPostAuthed(`/analyses/${analysisId}/explanation${force ? "?force=true" : ""}`, {}, token);
}
