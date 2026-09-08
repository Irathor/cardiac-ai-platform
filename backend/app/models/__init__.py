"""Importing this package registers every ORM model on Base.metadata and
resolves string-based relationship() forward references. Anything that needs
a fully configured mapper (Alembic autogenerate, the test DB fixture, the
app itself) must import app.models before using the ORM.
"""
from app.models.ai_analysis import AIAnalysis
from app.models.annotation import Annotation
from app.models.audit_event import AuditEvent
from app.models.biomarker_measurement import BiomarkerMeasurement
from app.models.clinical_review import ClinicalReview
from app.models.dataset import Dataset
from app.models.dataset_case import DatasetCase
from app.models.dataset_version import DatasetVersion
from app.models.image_series import ImageSeries
from app.models.imaging_study import ImagingStudy
from app.models.model_approval import ModelApproval
from app.models.model_evaluation import ModelEvaluation
from app.models.model_version import ModelVersion
from app.models.organization import Organization
from app.models.patient import Patient
from app.models.practitioner_patient_assignment import PractitionerPatientAssignment
from app.models.refresh_token import RefreshToken
from app.models.role import Role
from app.models.segmentation import Segmentation
from app.models.training_run import TrainingRun
from app.models.user import User
from app.models.user_role import UserRole

__all__ = [
    "AIAnalysis",
    "Annotation",
    "AuditEvent",
    "BiomarkerMeasurement",
    "ClinicalReview",
    "Dataset",
    "DatasetCase",
    "DatasetVersion",
    "ImageSeries",
    "ImagingStudy",
    "ModelApproval",
    "ModelEvaluation",
    "ModelVersion",
    "Organization",
    "Patient",
    "PractitionerPatientAssignment",
    "RefreshToken",
    "Role",
    "Segmentation",
    "TrainingRun",
    "User",
    "UserRole",
]
