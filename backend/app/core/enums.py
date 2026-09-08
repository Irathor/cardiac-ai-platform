"""Plain string enums for status/action columns — kept as strings in the DB
(see app.models.role for why) rather than native Postgres ENUM types."""
from enum import Enum


class StudyStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ReviewAction(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    CORRECTED = "CORRECTED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class AnalysisStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AnnotationStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class DatasetVersionStatus(str, Enum):
    DRAFT = "DRAFT"
    LOCKED = "LOCKED"


class DatasetSplit(str, Enum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"


class TrainingRunStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TrainingModelType(str, Enum):
    NEAREST_CENTROID = "NEAREST_CENTROID"
    UNET_SEGMENTATION = "UNET_SEGMENTATION"
    CNN3D_CLASSIFICATION = "CNN3D_CLASSIFICATION"


class ModelVersionStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PRODUCTION = "PRODUCTION"
    RETIRED = "RETIRED"


class ApprovalDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
