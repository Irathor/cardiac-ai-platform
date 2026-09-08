import { apiGetAuthed } from "./client";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1";

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
  created_at: string;
  completed_at: string | null;
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
