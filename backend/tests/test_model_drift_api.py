"""EPIC-7 (docs/epics/EPIC-7-deteccion-drift.md): GET /model-versions/{id}/drift.

Builds real DatasetCase/BiomarkerMeasurement/AIAnalysis rows (no mocking of
drift_service's own math — scipy's ks_2samp and the PSI formula run for
real) so a forced-shift scenario and a no-shift scenario genuinely exercise
the statistics, not just the plumbing around them."""
import uuid
from datetime import date, datetime, timedelta, timezone

from app.models.ai_analysis import AIAnalysis
from app.models.dataset import Dataset
from app.models.dataset_case import DatasetCase
from app.models.dataset_version import DatasetVersion
from app.services import drift_service
from tests.conftest import (
    make_annotation,
    make_model_version,
    make_patient,
    make_series,
    make_study,
    make_user,
)


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_dataset_version(db_session) -> DatasetVersion:
    dataset = Dataset(name=f"drift-test-{uuid.uuid4().hex[:8]}")
    db_session.add(dataset)
    db_session.flush()
    dataset_version = DatasetVersion(dataset_id=dataset.id, version_number=1, status="LOCKED")
    db_session.add(dataset_version)
    db_session.flush()
    return dataset_version


def _add_base_case(db_session, demo_org, *, dataset_version, annotator, value: float, index: int):
    """One DatasetCase whose walk (annotation -> segmentation -> series ->
    study) resolves to a single BiomarkerMeasurement("LVEF", value) — same
    path drift_service._biomarker_base_pool uses.

    The segmentation's `created_at` is deliberately backdated well past
    RECENT_WINDOW_MAX_DAYS (training happened before the model was even
    promoted) — otherwise it would double as its own "recent" sample too
    (list_recent_measurements_by_name filters only by
    Segmentation.created_at, with no awareness of DatasetCase membership),
    contaminating the recent pool's sample size."""
    from app.models.biomarker_measurement import BiomarkerMeasurement
    from app.models.segmentation import Segmentation

    patient = make_patient(db_session, demo_org, identifier=f"drift-base-{index}-{uuid.uuid4().hex[:6]}")
    study = make_study(db_session, patient=patient)
    series = make_series(db_session, study=study, phase="ED")
    old_created_at = datetime.now(timezone.utc) - timedelta(days=drift_service.RECENT_WINDOW_MAX_DAYS + 30)
    segmentation = Segmentation(
        image_series_id=series.id, storage_key=f"test/{series.id}/mask.nii.gz", created_at=old_created_at,
    )
    db_session.add(segmentation)
    db_session.flush()
    db_session.add(BiomarkerMeasurement(segmentation_id=segmentation.id, name="LVEF", value=value, unit="mL"))
    annotation = make_annotation(db_session, segmentation=segmentation, annotator=annotator)
    db_session.add(
        DatasetCase(
            dataset_version_id=dataset_version.id, patient_id=patient.id,
            annotation_id=annotation.id, split="TRAIN",
        )
    )
    db_session.commit()


def _add_recent_measurement(db_session, demo_org, *, value: float, days_ago: int = 1):
    """A Segmentation + BiomarkerMeasurement outside any DatasetCase, with a
    controlled `Segmentation.created_at` — this is the "recent" sample
    drift_service.segmentation_repository.list_recent_measurements_by_name
    reads, independent of the DatasetVersion base pool."""
    from app.models.biomarker_measurement import BiomarkerMeasurement
    from app.models.image_series import ImageSeries
    from app.models.imaging_study import ImagingStudy
    from app.models.patient import Patient
    from app.models.segmentation import Segmentation

    patient = Patient(
        organization_id=demo_org.id, identifier=f"drift-recent-{uuid.uuid4().hex[:8]}",
        first_name="Recent", last_name="Case", date_of_birth=date(2000, 1, 1),
    )
    db_session.add(patient)
    db_session.flush()
    study = ImagingStudy(patient_id=patient.id, study_date=date(2025, 1, 1), status="COMPLETED")
    db_session.add(study)
    db_session.flush()
    series = ImageSeries(
        imaging_study_id=study.id, series_type="CINE_SHORT_AXIS", phase="ED",
        storage_key=f"test/{study.id}/ed.nii.gz",
        voxel_spacing_x_mm=1.0, voxel_spacing_y_mm=1.0, voxel_spacing_z_mm=1.0,
        shape_x=10, shape_y=10, shape_z=10,
    )
    db_session.add(series)
    db_session.flush()
    created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    segmentation = Segmentation(
        image_series_id=series.id, storage_key=f"test/{series.id}/mask.nii.gz", created_at=created_at,
    )
    db_session.add(segmentation)
    db_session.flush()
    db_session.add(BiomarkerMeasurement(segmentation_id=segmentation.id, name="LVEF", value=value, unit="%"))
    db_session.commit()


def _make_analysis(db_session, demo_org, *, model_version, predicted_class: str, completed_at: datetime):
    from app.models.imaging_study import ImagingStudy
    from app.models.patient import Patient

    patient = Patient(
        organization_id=demo_org.id, identifier=f"drift-pred-{uuid.uuid4().hex[:8]}",
        first_name="Pred", last_name="Case", date_of_birth=date(2000, 1, 1),
    )
    db_session.add(patient)
    db_session.flush()
    study = ImagingStudy(patient_id=patient.id, study_date=date(2025, 1, 1), status="COMPLETED")
    db_session.add(study)
    db_session.flush()
    label = f"{model_version.name}@{model_version.id}"
    analysis = AIAnalysis(
        imaging_study_id=study.id, status="COMPLETED", model_version=label,
        predicted_class=predicted_class, probabilities={predicted_class: 0.9},
        confidence=0.9, completed_at=completed_at,
    )
    db_session.add(analysis)
    db_session.commit()


def _promote_to_production(client, db_session, demo_org, *, model_version, approver_email: str):
    make_user(db_session, demo_org, email=approver_email, role="MODEL_APPROVER")
    token = _login(client, approver_email)
    model_version.status = "APPROVED"
    db_session.commit()
    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/promote",
        headers=_auth(token), json={"justification": "Ship it for drift testing"},
    )
    assert response.status_code == 200
    db_session.refresh(model_version)
    return token


def test_drift_requires_production_status(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml-drift1@cardiacai-test.dev", role="ML_ENGINEER")
    model_version = make_model_version(db_session, status="APPROVED")
    token = _login(client, "ml-drift1@cardiacai-test.dev")

    response = client.get(f"/api/v1/model-versions/{model_version.id}/drift", headers=_auth(token))
    assert response.status_code == 409


def test_drift_endpoint_requires_view_role(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doc-drift1@cardiacai-test.dev", role="DOCTOR")
    model_version = make_model_version(db_session, status="APPROVED")
    token = _login(client, "doc-drift1@cardiacai-test.dev")

    response = client.get(f"/api/v1/model-versions/{model_version.id}/drift", headers=_auth(token))
    assert response.status_code == 403


def test_drift_not_found_for_unknown_model_version(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml-drift2@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml-drift2@cardiacai-test.dev")

    response = client.get(f"/api/v1/model-versions/{uuid.uuid4()}/drift", headers=_auth(token))
    assert response.status_code == 404


def test_biomarker_and_prediction_drift_detected_with_a_forced_shift(client, db_session, demo_org):
    dataset_version = _make_dataset_version(db_session)
    annotator = make_user(db_session, demo_org, email="annotator-drift1@cardiacai-test.dev", role="ANNOTATOR")

    # Base population: LVEF clustered around 60 (30 cases).
    base_values = [55 + i * (10 / 29) for i in range(30)]  # 55..65
    for i, value in enumerate(base_values):
        _add_base_case(db_session, demo_org, dataset_version=dataset_version, annotator=annotator, value=value, index=i)

    model_version = make_model_version(db_session, dataset_version=dataset_version, status="APPROVED")
    _promote_to_production(client, db_session, demo_org, model_version=model_version, approver_email="approver-drift1@cardiacai-test.dev")

    # Recent population: LVEF clustered around 20 — a clear, deliberate shift.
    recent_values = [15 + i * (10 / 29) for i in range(30)]  # 15..25
    for value in recent_values:
        _add_recent_measurement(db_session, demo_org, value=value, days_ago=1)

    # Base prediction window: promotion just happened, so anchor right after it.
    promotion_time = datetime.now(timezone.utc)
    for i in range(30):
        _make_analysis(
            db_session, demo_org, model_version=model_version, predicted_class="NORMAL",
            completed_at=promotion_time + timedelta(minutes=i + 1),
        )
    # Recent prediction window: predominantly a different class — forced shift.
    for i in range(30):
        _make_analysis(
            db_session, demo_org, model_version=model_version, predicted_class="DILATED_CARDIOMYOPATHY",
            completed_at=datetime.now(timezone.utc) - timedelta(hours=1) + timedelta(minutes=i),
        )

    make_user(db_session, demo_org, email="ml-drift3@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml-drift3@cardiacai-test.dev")

    response = client.get(f"/api/v1/model-versions/{model_version.id}/drift", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()

    assert body["biomarkers_skipped_reason"] is None
    lvef = next(b for b in body["biomarkers"] if b["biomarker_name"] == "LVEF")
    assert lvef["skipped_reason"] is None
    assert lvef["base_sample_size"] == 30
    assert lvef["recent_sample_size"] == 30
    assert lvef["p_value"] < 0.05
    assert lvef["drift_detected"] is True

    prediction = body["prediction"]
    assert prediction["skipped_reason"] is None
    assert prediction["psi"] > 0.2
    assert prediction["severity"] == "SIGNIFICANT"
    assert prediction["drift_detected"] is True

    # Metrics reflect the result of this call (EPIC-7 point 5) — recalculated
    # only as a side effect of the endpoint, never on scrape.
    metrics_response = client.get("/metrics")
    assert metrics_response.status_code == 200
    metrics_text = metrics_response.text
    assert "biomarker_drift_ks_statistic" in metrics_text
    assert "biomarker_drift_pvalue" in metrics_text
    assert "prediction_drift_psi" in metrics_text
    assert str(model_version.id) in metrics_text
    assert "LVEF" in metrics_text


def test_no_drift_with_equivalent_recent_and_base_distributions(client, db_session, demo_org):
    dataset_version = _make_dataset_version(db_session)
    annotator = make_user(db_session, demo_org, email="annotator-drift2@cardiacai-test.dev", role="ANNOTATOR")

    base_values = [55 + i * (10 / 29) for i in range(30)]  # 55..65
    for i, value in enumerate(base_values):
        _add_base_case(db_session, demo_org, dataset_version=dataset_version, annotator=annotator, value=value, index=i)

    model_version = make_model_version(db_session, dataset_version=dataset_version, status="APPROVED")
    _promote_to_production(client, db_session, demo_org, model_version=model_version, approver_email="approver-drift2@cardiacai-test.dev")

    # Recent population: same distribution as base — no drift expected.
    for value in base_values:
        _add_recent_measurement(db_session, demo_org, value=value, days_ago=1)

    promotion_time = datetime.now(timezone.utc)
    labels = ["NORMAL", "DILATED_CARDIOMYOPATHY", "HYPERTROPHIC_CARDIOMYOPATHY", "MYOCARDIAL_INFARCTION", "ABNORMAL_RIGHT_VENTRICLE"]
    for i in range(30):
        _make_analysis(
            db_session, demo_org, model_version=model_version, predicted_class=labels[i % len(labels)],
            completed_at=promotion_time + timedelta(minutes=i + 1),
        )
    for i in range(30):
        _make_analysis(
            db_session, demo_org, model_version=model_version, predicted_class=labels[i % len(labels)],
            completed_at=datetime.now(timezone.utc) - timedelta(hours=1) + timedelta(minutes=i),
        )

    make_user(db_session, demo_org, email="ml-drift4@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml-drift4@cardiacai-test.dev")

    response = client.get(f"/api/v1/model-versions/{model_version.id}/drift", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()

    lvef = next(b for b in body["biomarkers"] if b["biomarker_name"] == "LVEF")
    assert lvef["skipped_reason"] is None
    assert lvef["p_value"] >= 0.05
    assert lvef["drift_detected"] is False

    prediction = body["prediction"]
    assert prediction["skipped_reason"] is None
    assert prediction["psi"] < 0.1
    assert prediction["severity"] == "NONE"
    assert prediction["drift_detected"] is False


def test_biomarker_drift_skipped_for_a_dl_production_model_without_a_dataset_version(client, db_session, demo_org):
    """UNET_SEGMENTATION/CNN3D_CLASSIFICATION training runs don't consume a
    DatasetVersion (EPIC-7 point 2 of the "Contrato técnico") — the
    biomarker section is omitted with an explicit reason instead of
    crashing or silently reporting an empty list with no explanation."""
    from app.core.enums import TrainingRunStatus
    from app.models.training_run import TrainingRun

    training_run = TrainingRun(dataset_version_id=None, model_type="CNN3D_CLASSIFICATION", status=TrainingRunStatus.COMPLETED.value)
    db_session.add(training_run)
    db_session.flush()

    import mlflow

    from app.services.training_service import _register_raw_artifact_model_version
    import os

    name = f"cnn3d-drift-test-{uuid.uuid4().hex[:8]}"
    mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
    mlflow.set_experiment(name)
    with mlflow.start_run(run_name=f"test-fixture-{uuid.uuid4().hex[:8]}") as run:
        mlflow.log_dict({}, "weights.json")
        run_id = run.info.run_id
    registered = _register_raw_artifact_model_version(name=name, run_id=run_id, artifact_path="weights.json")

    from app.models.model_version import ModelVersion

    model_version = ModelVersion(
        training_run_id=training_run.id, name=name, mlflow_run_id=run_id,
        mlflow_model_uri="file:///tmp/weights.json", prototypes=None, status="APPROVED",
        mlflow_registry_name=registered.name, mlflow_registry_version=registered.version,
    )
    db_session.add(model_version)
    db_session.commit()

    _promote_to_production(client, db_session, demo_org, model_version=model_version, approver_email="approver-drift3@cardiacai-test.dev")

    make_user(db_session, demo_org, email="ml-drift5@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml-drift5@cardiacai-test.dev")

    response = client.get(f"/api/v1/model-versions/{model_version.id}/drift", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["biomarkers"] == []
    assert body["biomarkers_skipped_reason"] == (
        "production model type CNN3D_CLASSIFICATION was not trained against a DatasetVersion"
    )
    # No promotion-anchored predictions were created for this model, so the
    # prediction side is skipped too — for a different, honest reason.
    assert body["prediction"]["skipped_reason"] is not None
    assert body["prediction"]["drift_detected"] is False
