import uuid
from datetime import datetime

from pydantic import BaseModel


class ImageSeriesOut(BaseModel):
    id: uuid.UUID
    imaging_study_id: uuid.UUID
    series_type: str
    phase: str | None
    voxel_spacing_x_mm: float
    voxel_spacing_y_mm: float
    voxel_spacing_z_mm: float
    shape_x: int
    shape_y: int
    shape_z: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BiomarkerMeasurementOut(BaseModel):
    id: uuid.UUID
    name: str
    value: float
    unit: str

    model_config = {"from_attributes": True}


class SegmentationOut(BaseModel):
    id: uuid.UUID
    image_series_id: uuid.UUID
    model_version: str | None
    created_at: datetime
    biomarker_measurements: list[BiomarkerMeasurementOut] = []

    model_config = {"from_attributes": True}
