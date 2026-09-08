import { apiGetAuthed } from "./client";

export interface DatasetOut {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}

export interface DatasetVersionOut {
  id: string;
  dataset_id: string;
  version_number: number;
  status: string;
  checksum: string | null;
  created_at: string;
  locked_at: string | null;
}

export function listDatasets(token: string): Promise<DatasetOut[]> {
  return apiGetAuthed("/datasets", token);
}

export function listDatasetVersions(datasetId: string, token: string): Promise<DatasetVersionOut[]> {
  return apiGetAuthed(`/datasets/${datasetId}/versions`, token);
}
