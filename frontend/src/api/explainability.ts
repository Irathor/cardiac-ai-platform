import { apiGetAuthed, apiGetBlobAuthed } from "./client";

/**
 * Client for the read-only showcase endpoints added in EPIC-15 — see
 * `docs/epics/EPIC-15-showcase-lime-vs-shapley.md` "Contrato técnico".
 * Both endpoints only serve artifacts already generated offline by
 * `ml/scripts/run_explainability_showcase.py` (EPIC-1); nothing here
 * recalculates Grad-CAM, LIME, or Shapley.
 *
 * Typed laxly on the wire (mirrors the backend's `ExplainabilityShowcaseOut`,
 * itself a deliberate passthrough — see the schema's docstring): the exact
 * shape is owned by the offline script, not a strict API contract. The
 * interfaces below describe the fields this page actually reads, not every
 * field the script happens to write today.
 */

export interface UnetStructureGradCam {
  png_path: string;
  attribution_mean?: number;
  attribution_max?: number;
  [key: string]: unknown;
}

export interface UnetSegGradCam {
  patient_id?: string;
  slice_index?: number;
  structures: Record<string, UnetStructureGradCam>;
  [key: string]: unknown;
}

export interface Cnn3dGradCam {
  patient_id?: string;
  true_class?: string;
  predicted_class?: string;
  png_path: string;
  attribution_mean?: number;
  attribution_max?: number;
  [key: string]: unknown;
}

/** Keys are the literal, pre-fixed labels from ADR-3 — `"LIME (aproximado)"`
 * / `"Shapley (exacto)"` — never renamed by the frontend (see EPIC-15). */
export type MethodAttributions = Record<string, Record<string, number>>;

export interface LimeShapleyPanel {
  patient_id?: string;
  predicted_class?: string;
  method_attributions: MethodAttributions;
  note?: string;
  [key: string]: unknown;
}

export interface ExplainabilityShowcase {
  unet_seg_grad_cam: UnetSegGradCam;
  cnn3d_grad_cam: Cnn3dGradCam;
  lime_shapley_panel: LimeShapleyPanel;
}

export function fetchExplainabilityShowcase(token: string): Promise<ExplainabilityShowcase> {
  return apiGetAuthed("/explainability/showcase", token);
}

export function fetchExplainabilityShowcaseImage(filename: string, token: string): Promise<Blob> {
  return apiGetBlobAuthed(`/explainability/showcase/images/${encodeURIComponent(filename)}`, token);
}

/** `png_path` in the JSON is a filesystem path written by the offline script
 * (backslash-separated on Windows) — the image endpoint only accepts a bare
 * basename (see the backend's allowlist), so this extracts it regardless of
 * which separator the path was written with. */
export function pngBasename(pngPath: string): string {
  const parts = pngPath.split(/[/\\]/);
  return parts[parts.length - 1];
}
