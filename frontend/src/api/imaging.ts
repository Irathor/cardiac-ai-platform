import { apiGetAuthed, apiGetBlobAuthed } from "./client";

export interface ImageSeries {
  id: string;
  imaging_study_id: string;
  series_type: string;
  phase: string | null;
  voxel_spacing_x_mm: number;
  voxel_spacing_y_mm: number;
  voxel_spacing_z_mm: number;
  shape_x: number;
  shape_y: number;
  shape_z: number;
  created_at: string;
}

export interface BiomarkerMeasurement {
  id: string;
  name: string;
  value: number;
  unit: string;
}

export interface Segmentation {
  id: string;
  image_series_id: string;
  model_version: string | null;
  created_at: string;
  biomarker_measurements: BiomarkerMeasurement[];
}

export function fetchSeriesForStudy(studyId: string, token: string): Promise<ImageSeries[]> {
  return apiGetAuthed(`/studies/${studyId}/series`, token);
}

export function fetchSeriesFile(seriesId: string, token: string): Promise<Blob> {
  return apiGetBlobAuthed(`/series/${seriesId}/file`, token);
}

export function fetchSegmentationsForSeries(seriesId: string, token: string): Promise<Segmentation[]> {
  return apiGetAuthed(`/series/${seriesId}/segmentations`, token);
}

export function fetchSegmentationFile(segmentationId: string, token: string): Promise<Blob> {
  return apiGetBlobAuthed(`/segmentations/${segmentationId}/file`, token);
}

export function fetchBiomarkers(segmentationId: string, token: string): Promise<BiomarkerMeasurement[]> {
  return apiGetAuthed(`/segmentations/${segmentationId}/biomarkers`, token);
}
