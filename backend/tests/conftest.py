"""Shared test fixtures: an in-memory SQLite database (via the portable GUID
type in app.db.types) so DB-touching code can be verified without a live
Postgres instance. Integration tests against real Postgres/Redis/MinIO run
separately inside Docker Compose (see docs/architecture.md)."""
import os
import tempfile
import uuid
from pathlib import Path

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")
os.environ.setdefault("POSTGRES_PASSWORD", "test-password")
os.environ.setdefault("MINIO_ACCESS_KEY", "test-access-key")
os.environ.setdefault("MINIO_SECRET_KEY", "test-secret-key")
# Real mlflow client, pointed at a local sqlite-backed store instead of a
# server — no Docker/network needed, but app.services.training_service's
# and app.services.model_service's mlflow calls (including
# register_model/transition_model_version_stage, EPIC-4) are genuinely
# exercised rather than mocked. Real server-backed tracking is verified
# separately inside Docker Compose. A plain file store (mlflow's default)
# does NOT support the Model Registry — register_model/transition_model_version_stage
# require a database-backed store, hence sqlite here instead of file://.
# as_posix() keeps the URI well-formed on Windows ("sqlite:///C:/...").
os.environ.setdefault(
    "MLFLOW_TRACKING_URI",
    f"sqlite:///{Path(tempfile.mkdtemp(prefix='mlflow-test-')).as_posix()}/mlflow.db",
)

import mlflow.tracking._tracking_service.utils as mlflow_tracking_utils
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.session as db_session_module
import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.celery_app import celery_app
from app.core.roles import RoleName
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.organization import Organization
from app.models.role import Role
from app.repositories import user_repository
from app.storage import object_storage

# No Redis/worker in the test environment — tasks run inline, synchronously,
# in the same process and DB transaction context as the test itself.
celery_app.conf.task_always_eager = True
celery_app.conf.task_eager_propagates = True

# A SQLAlchemy-backed mlflow store (used above instead of a file:// store,
# see the MLFLOW_TRACKING_URI comment above) falls back to creating
# "./mlruns" *relative to the process's CWD* for any experiment without an
# explicit artifact location — including its own auto-created "Default"
# experiment, a side effect of the very first store connection. Redirecting
# that fallback into the same tempdir as the tracking DB keeps every test
# artifact contained instead of littering the repo root with a stray
# mlruns/ directory on every test run. Path.as_uri() (not a plain path
# string) so Windows drive letters like "C:\..." never get misparsed as a
# URI scheme by mlflow's urlparse-based artifact repository lookup.
mlflow_tracking_utils.DEFAULT_LOCAL_FILE_AND_ARTIFACT_PATH = (
    Path(tempfile.mkdtemp(prefix="mlflow-artifacts-test-")).as_uri()
)


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)


@pytest.fixture
def db_session(engine) -> Session:
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def client(engine, monkeypatch):
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def _override_get_db():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    # Celery tasks (run eagerly in tests, see task_always_eager above) open
    # their own session via app.db.session.get_session_factory() instead of
    # the get_db dependency — point that at the same test engine so a task
    # triggered mid-request sees the request's own data.
    monkeypatch.setattr(db_session_module, "get_session_factory", lambda: session_factory)
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.clear()


class FakeObjectStorage:
    """MinIO stand-in for tests — see docs/architecture.md; real storage is
    verified separately inside Docker Compose."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._data[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self._data[key]


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    fake = FakeObjectStorage()
    monkeypatch.setattr(object_storage, "get_storage", lambda: fake)
    return fake


@pytest.fixture
def demo_org(db_session) -> Organization:
    org = Organization(name="Test Org")
    db_session.add(org)
    db_session.flush()
    for role_name in RoleName:
        db_session.add(Role(name=role_name.value, description=role_name.value))
    db_session.commit()
    return org


def make_user(db_session, demo_org, *, email: str, role: str, password: str = "Str0ng-Password!"):
    """Test helper: creates a user with a single role and a known password."""
    user = user_repository.create(
        db_session,
        organization_id=demo_org.id,
        email=email,
        full_name=email.split("@")[0],
        password_hash=hash_password(password),
    )
    role_row = user_repository.get_role_by_name(db_session, role)
    user_repository.assign_role(db_session, user_id=user.id, role_id=role_row.id, assigned_by=None)
    db_session.commit()
    return user


def make_patient(
    db_session,
    demo_org,
    *,
    identifier: str,
    first_name: str = "Jane",
    last_name: str = "Doe",
    dob="2000-01-01",
    registered_diagnosis=None,
):
    from datetime import date as date_cls

    from app.models.patient import Patient

    if isinstance(dob, str):
        dob = date_cls.fromisoformat(dob)
    patient = Patient(
        organization_id=demo_org.id,
        identifier=identifier,
        first_name=first_name,
        last_name=last_name,
        date_of_birth=dob,
        registered_diagnosis=registered_diagnosis,
    )
    db_session.add(patient)
    db_session.commit()
    return patient


def assign_doctor(db_session, *, patient, doctor):
    from app.models.practitioner_patient_assignment import PractitionerPatientAssignment

    db_session.add(
        PractitionerPatientAssignment(patient_id=patient.id, doctor_user_id=doctor.id)
    )
    db_session.commit()


def make_study(db_session, *, patient, study_date="2026-01-01", status="COMPLETED"):
    from datetime import date as date_cls

    from app.models.imaging_study import ImagingStudy

    if isinstance(study_date, str):
        study_date = date_cls.fromisoformat(study_date)
    study = ImagingStudy(patient_id=patient.id, study_date=study_date, status=status)
    db_session.add(study)
    db_session.commit()
    return study


def make_series(db_session, *, study, phase=None, series_type="CINE_SHORT_AXIS"):
    from app.models.image_series import ImageSeries

    series = ImageSeries(
        imaging_study_id=study.id,
        series_type=series_type,
        phase=phase,
        storage_key=f"test/{study.id}/{phase or 'series'}.nii.gz",
        voxel_spacing_x_mm=1.0,
        voxel_spacing_y_mm=1.0,
        voxel_spacing_z_mm=1.0,
        shape_x=10,
        shape_y=10,
        shape_z=10,
    )
    db_session.add(series)
    db_session.commit()
    return series


def make_annotation(db_session, *, segmentation, annotator, status="APPROVED", diagnosis_label="NORMAL"):
    from app.models.annotation import Annotation

    annotation = Annotation(
        based_on_segmentation_id=segmentation.id,
        annotator_id=annotator.id,
        status=status,
        diagnosis_label=diagnosis_label,
    )
    db_session.add(annotation)
    db_session.commit()
    return annotation


def make_model_version(
    db_session, *, name="cardiac-classifier", status="PENDING_REVIEW", prototypes=None, dataset_version=None,
):
    """Also registers a real MLflow Registry entry (same sqlite-backed store
    as app.services.training_service, see conftest's MLFLOW_TRACKING_URI) so
    that app.services.model_service.review()/promote()/check_registry_divergence
    — which call the real MlflowClient — have a genuine registered version
    to transition/inspect, instead of every caller having to mock MLflow
    individually (see EPIC-4)."""
    import mlflow

    from app.core.enums import DatasetVersionStatus, TrainingRunStatus
    from app.models.dataset import Dataset
    from app.models.dataset_version import DatasetVersion
    from app.models.model_version import ModelVersion
    from app.models.training_run import TrainingRun

    if dataset_version is None:
        dataset = Dataset(name=f"test-dataset-{uuid.uuid4().hex[:8]}")
        db_session.add(dataset)
        db_session.flush()
        dataset_version = DatasetVersion(dataset_id=dataset.id, version_number=1, status=DatasetVersionStatus.LOCKED.value)
        db_session.add(dataset_version)
        db_session.flush()

    training_run = TrainingRun(dataset_version_id=dataset_version.id, status=TrainingRunStatus.COMPLETED.value)
    db_session.add(training_run)
    db_session.flush()

    if prototypes is None:
        from cardiac_ai_ml.classification import DiagnosisClass, FEATURE_NAMES

        prototypes = {d.value: dict.fromkeys(FEATURE_NAMES, 100.0) for d in DiagnosisClass}

    # Registers through the same helper training_service.py uses (not
    # mlflow.register_model directly) — see its docstring: mlflow>=3's
    # register_model needs an MLmodel file or a Logged Model for a runs:/
    # URI, neither of which a plain mlflow.log_dict artifact has.
    from app.services.training_service import _register_raw_artifact_model_version

    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment(name)
    with mlflow.start_run(run_name=f"test-fixture-{uuid.uuid4().hex[:8]}") as run:
        mlflow.log_dict(prototypes, "prototypes.json")
        run_id = run.info.run_id
    registered = _register_raw_artifact_model_version(name=name, run_id=run_id, artifact_path="prototypes.json")

    model_version = ModelVersion(
        training_run_id=training_run.id, name=name, mlflow_run_id=run_id,
        mlflow_model_uri="file:///tmp/prototypes.json", prototypes=prototypes, status=status,
        mlflow_registry_name=registered.name, mlflow_registry_version=registered.version,
    )
    db_session.add(model_version)
    db_session.commit()
    return model_version


def make_ai_analysis(db_session, *, study, predicted_class: str, confidence: float, status: str = "COMPLETED"):
    from app.models.ai_analysis import AIAnalysis

    analysis = AIAnalysis(
        imaging_study_id=study.id,
        status=status,
        model_version="test-fixture",
        predicted_class=predicted_class,
        probabilities={predicted_class: confidence},
        confidence=confidence,
    )
    db_session.add(analysis)
    db_session.commit()
    return analysis


def make_segmentation_with_biomarkers(db_session, *, series, biomarkers: dict):
    from app.models.biomarker_measurement import BiomarkerMeasurement
    from app.models.segmentation import Segmentation

    segmentation = Segmentation(image_series_id=series.id, storage_key=f"test/{series.id}/mask.nii.gz")
    db_session.add(segmentation)
    db_session.flush()
    for name, value in biomarkers.items():
        db_session.add(
            BiomarkerMeasurement(segmentation_id=segmentation.id, name=name, value=value, unit="mL")
        )
    db_session.commit()
    return segmentation
