"""Training pipeline: "smoke training" (see ml.cardiac_ai_ml.training) runs
eagerly in tests (see conftest.py's task_always_eager) against a real, local
file-backed MLflow tracking store (see conftest.py's MLFLOW_TRACKING_URI) —
so this genuinely exercises app.services.training_service's mlflow calls,
not a mock. Real server-backed tracking is verified separately inside Docker
Compose."""
import json

import httpx
import pytest

from app.core.enums import TrainingModelType, TrainingRunStatus
from app.core.model_registry import MODEL_NAME_CNN3D, MODEL_NAME_UNET
from app.models.training_run import TrainingRun
from app.repositories import model_repository
from app.services import training_service
from tests.conftest import (
    make_annotation,
    make_patient,
    make_segmentation_with_biomarkers,
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


# (label, ed_lv, es_lv, rv, mass) — five separable profiles, one per
# DiagnosisClass, loosely mirroring ml.cardiac_ai_ml.classification's own
# demo prototypes so the fitted centroids should recover them cleanly.
_CLASS_PROFILES = [
    ("NORMAL", 140.0, 49.0, 140.0, 120.0),
    ("DILATED_CARDIOMYOPATHY", 260.0, 195.0, 140.0, 150.0),
    ("HYPERTROPHIC_CARDIOMYOPATHY", 110.0, 38.5, 110.0, 200.0),
    ("MYOCARDIAL_INFARCTION", 160.0, 104.0, 140.0, 120.0),
    ("ABNORMAL_RIGHT_VENTRICLE", 140.0, 56.0, 220.0, 110.0),
]


def _make_case(db_session, demo_org, *, identifier, annotator, label, ed_lv, es_lv, rv, mass):
    patient = make_patient(db_session, demo_org, identifier=identifier)
    study = make_study(db_session, patient=patient)
    ed_series = make_series(db_session, study=study, phase="ED")
    ed_segmentation = make_segmentation_with_biomarkers(
        db_session, series=ed_series,
        biomarkers={"LV_VOLUME": ed_lv, "RV_VOLUME": rv, "MYOCARDIAL_VOLUME": mass / 1.05, "MYOCARDIAL_MASS": mass},
    )
    es_series = make_series(db_session, study=study, phase="ES")
    make_segmentation_with_biomarkers(
        db_session, series=es_series,
        biomarkers={"LV_VOLUME": es_lv, "RV_VOLUME": rv * 0.4, "MYOCARDIAL_VOLUME": mass / 1.05, "MYOCARDIAL_MASS": mass},
    )
    return make_annotation(
        db_session, segmentation=ed_segmentation, annotator=annotator, status="APPROVED", diagnosis_label=label
    )


def _setup_locked_version_with_all_classes(client, db_session, demo_org, *, suffix):
    _engineer = make_user(db_session, demo_org, email=f"ml-t{suffix}@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email=f"annot-t{suffix}@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, f"ml-t{suffix}@cardiacai-test.dev")

    dataset = client.post("/api/v1/datasets", headers=_auth(token), json={"name": f"Training dataset {suffix}"}).json()
    version = client.post(f"/api/v1/datasets/{dataset['id']}/versions", headers=_auth(token)).json()

    for i, (label, ed_lv, es_lv, rv, mass) in enumerate(_CLASS_PROFILES):
        annotation = _make_case(
            db_session, demo_org, identifier=f"PT-TRAIN-{suffix}-{i}", annotator=annotator,
            label=label, ed_lv=ed_lv, es_lv=es_lv, rv=rv, mass=mass,
        )
        client.post(
            f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/cases",
            headers=_auth(token), json={"annotation_id": str(annotation.id), "split": "TRAIN"},
        ).raise_for_status()

    # One TEST case, reusing the NORMAL profile almost exactly.
    test_annotation = _make_case(
        db_session, demo_org, identifier=f"PT-TRAIN-{suffix}-test", annotator=annotator,
        label="NORMAL", ed_lv=141.0, es_lv=50.0, rv=139.0, mass=121.0,
    )
    client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/cases",
        headers=_auth(token), json={"annotation_id": str(test_annotation.id), "split": "TEST"},
    ).raise_for_status()

    lock_response = client.post(f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/lock", headers=_auth(token))
    assert lock_response.status_code == 200

    return token, dataset["id"], version["id"]


def test_training_run_completes_and_registers_a_model_version(client, db_session, demo_org):
    token, dataset_id, version_id = _setup_locked_version_with_all_classes(client, db_session, demo_org, suffix="1")

    run = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/training-runs", headers=_auth(token),
    )
    assert run.status_code == 202
    run_id = run.json()["id"]

    fetched = client.get(f"/api/v1/training-runs/{run_id}", headers=_auth(token))
    body = fetched.json()
    assert body["status"] == "COMPLETED"
    assert body["mlflow_run_id"] is not None
    assert body["metrics"]["test_accuracy"] == pytest.approx(1.0)
    assert body["metrics"]["train_case_count"] == 5

    versions = client.get("/api/v1/model-versions", headers=_auth(token))
    assert versions.status_code == 200
    assert len(versions.json()) == 1
    model_version = versions.json()[0]
    assert model_version["status"] == "PENDING_REVIEW"
    assert model_version["mlflow_model_uri"].endswith("prototypes.json")

    evaluations = client.get(f"/api/v1/model-versions/{model_version['id']}/evaluations", headers=_auth(token))
    assert evaluations.status_code == 200
    assert evaluations.json()[0]["split"] == "TEST"
    assert evaluations.json()[0]["accuracy"] == pytest.approx(1.0)


def test_training_requires_a_locked_dataset_version(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml-t2@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml-t2@cardiacai-test.dev")

    dataset = client.post("/api/v1/datasets", headers=_auth(token), json={"name": "Unlocked dataset"}).json()
    version = client.post(f"/api/v1/datasets/{dataset['id']}/versions", headers=_auth(token)).json()

    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/training-runs", headers=_auth(token),
    )
    assert response.status_code == 409


def test_training_fails_gracefully_when_a_class_is_missing_from_train(client, db_session, demo_org):
    _engineer = make_user(db_session, demo_org, email="ml-t3@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email="annot-t3@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, "ml-t3@cardiacai-test.dev")

    dataset = client.post("/api/v1/datasets", headers=_auth(token), json={"name": "Incomplete dataset"}).json()
    version = client.post(f"/api/v1/datasets/{dataset['id']}/versions", headers=_auth(token)).json()

    # Only NORMAL cases — the other 4 classes are missing from TRAIN.
    annotation = _make_case(
        db_session, demo_org, identifier="PT-TRAIN-3-only", annotator=annotator,
        label="NORMAL", ed_lv=140.0, es_lv=49.0, rv=140.0, mass=120.0,
    )
    client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/cases",
        headers=_auth(token), json={"annotation_id": str(annotation.id), "split": "TRAIN"},
    ).raise_for_status()
    client.post(f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/lock", headers=_auth(token))

    run = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/training-runs", headers=_auth(token),
    )
    run_id = run.json()["id"]

    fetched = client.get(f"/api/v1/training-runs/{run_id}", headers=_auth(token)).json()
    assert fetched["status"] == "FAILED"
    assert "class" in fetched["error_message"].lower() or "MISSING" in fetched["error_message"].upper()


def test_non_ml_engineer_cannot_start_training(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doc-t4@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc-t4@cardiacai-test.dev")

    response = client.post(
        "/api/v1/datasets/00000000-0000-0000-0000-000000000000/versions/00000000-0000-0000-0000-000000000000/training-runs",
        headers=_auth(token),
    )
    assert response.status_code == 403


def test_training_run_defaults_to_nearest_centroid_model_type(client, db_session, demo_org):
    token, dataset_id, version_id = _setup_locked_version_with_all_classes(client, db_session, demo_org, suffix="mt1")

    run = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/training-runs", headers=_auth(token),
    )
    assert run.status_code == 202
    assert run.json()["model_type"] == "NEAREST_CENTROID"


def test_training_run_accepts_explicit_nearest_centroid_model_type(client, db_session, demo_org):
    token, dataset_id, version_id = _setup_locked_version_with_all_classes(client, db_session, demo_org, suffix="mt2")

    run = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/training-runs",
        headers=_auth(token), json={"model_type": "NEAREST_CENTROID"},
    )
    assert run.status_code == 202
    assert run.json()["model_type"] == "NEAREST_CENTROID"

    fetched = client.get(f"/api/v1/training-runs/{run.json()['id']}", headers=_auth(token))
    assert fetched.json()["status"] == "COMPLETED"


def test_admin_can_trigger_and_view_training_runs_and_model_versions(client, db_session, demo_org):
    """ADMIN is an additive role on top of ML_ENGINEER (docs/permissions.md)
    — the nearest-centroid path itself is unchanged, only who may call it.
    Dataset/version management stays ML_ENGINEER-only (out of scope for this
    feature) — only training-runs and model-versions get the ADMIN role added."""
    make_user(db_session, demo_org, email="ml-t5@cardiacai-test.dev", role="ML_ENGINEER")
    make_user(db_session, demo_org, email="admin-t5@cardiacai-test.dev", role="ADMIN")
    annotator = make_user(db_session, demo_org, email="annot-t5@cardiacai-test.dev", role="ANNOTATOR")
    engineer_token = _login(client, "ml-t5@cardiacai-test.dev")
    admin_token = _login(client, "admin-t5@cardiacai-test.dev")

    dataset = client.post("/api/v1/datasets", headers=_auth(engineer_token), json={"name": "Admin dataset"}).json()
    version = client.post(f"/api/v1/datasets/{dataset['id']}/versions", headers=_auth(engineer_token)).json()
    for i, (label, ed_lv, es_lv, rv, mass) in enumerate(_CLASS_PROFILES):
        annotation = _make_case(
            db_session, demo_org, identifier=f"PT-ADMIN-{i}", annotator=annotator,
            label=label, ed_lv=ed_lv, es_lv=es_lv, rv=rv, mass=mass,
        )
        client.post(
            f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/cases",
            headers=_auth(engineer_token), json={"annotation_id": str(annotation.id), "split": "TRAIN"},
        ).raise_for_status()
    test_annotation = _make_case(
        db_session, demo_org, identifier="PT-ADMIN-test", annotator=annotator,
        label="NORMAL", ed_lv=141.0, es_lv=50.0, rv=139.0, mass=121.0,
    )
    client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/cases",
        headers=_auth(engineer_token), json={"annotation_id": str(test_annotation.id), "split": "TEST"},
    ).raise_for_status()
    client.post(f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/lock", headers=_auth(engineer_token))

    run = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/training-runs", headers=_auth(admin_token),
    )
    assert run.status_code == 202

    listed = client.get(
        f"/api/v1/datasets/{dataset['id']}/versions/{version['id']}/training-runs", headers=_auth(admin_token)
    )
    assert listed.status_code == 200

    fetched = client.get(f"/api/v1/training-runs/{run.json()['id']}", headers=_auth(admin_token))
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "COMPLETED"

    versions = client.get("/api/v1/model-versions", headers=_auth(admin_token))
    assert versions.status_code == 200
    assert len(versions.json()) >= 1

    evaluations = client.get(
        f"/api/v1/model-versions/{versions.json()[0]['id']}/evaluations", headers=_auth(admin_token)
    )
    assert evaluations.status_code == 200


# --- execute_dl_training: the runner is always mocked over HTTP here (see
# ml/scripts/training_runner_service.py) — no GPU/.venv-dl needed to verify
# this plumbing, only that real fixture JSON round-trips correctly. ---


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


def _make_dl_run(db_session, *, model_type: str) -> TrainingRun:
    run = TrainingRun(dataset_version_id=None, model_type=model_type, status=TrainingRunStatus.QUEUED.value)
    db_session.add(run)
    db_session.commit()
    return run


def _patch_data_root(monkeypatch, tmp_path) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "data_root", str(tmp_path))


_UNET_METRICS_FIXTURE = {
    "best_val_mean_dice_foreground": 0.84,
    "best_epoch": 43,
    "total_epochs": 60,
    "time_to_best_epoch_s": 1050.3,
    "degradation_since_best_epoch": 0.01,
    "test": {"per_class_dice": [0.99, 0.9, 0.75, 0.8], "mean_dice_foreground": 0.83},
    "detailed_validation": {"structures": ["LV", "RV", "MYO"], "phases": ["ED", "ES"], "patient_count": 2},
    "history": [{"epoch": 1, "train_loss": 0.5, "epoch_time_s": 10.0, "per_class_dice": [0.5, 0.5, 0.5, 0.5], "mean_dice_foreground": 0.5}],
    "train_patients": ["patient001"], "val_patients": ["patient002"], "test_patients": ["patient003"],
}


def test_execute_dl_training_unet_happy_path(db_session, tmp_path, monkeypatch):
    run = _make_dl_run(db_session, model_type=TrainingModelType.UNET_SEGMENTATION.value)
    _patch_data_root(monkeypatch, tmp_path)

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    (models_dir / "unet2d.pt").write_bytes(b"fake-weights")
    (models_dir / "unet2d.metrics.json").write_text(json.dumps(_UNET_METRICS_FIXTURE))

    get_calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        assert url.endswith("/jobs")
        assert json["model_type"] == "UNET_SEGMENTATION"
        return _FakeResponse({"job_id": "job-unet-1"})

    def fake_get(url, timeout=None):
        get_calls["n"] += 1
        if get_calls["n"] == 1:
            return _FakeResponse({"status": "RUNNING", "log_tail": "epoch 1...", "result_path": None, "error": None})
        return _FakeResponse(
            {"status": "COMPLETED", "log_tail": "done", "result_path": "models/unet2d.metrics.json", "error": None}
        )

    monkeypatch.setattr(training_service.httpx, "post", fake_post)
    monkeypatch.setattr(training_service.httpx, "get", fake_get)
    monkeypatch.setattr(training_service.time, "sleep", lambda s: None)

    training_service.execute_dl_training(db_session, training_run_id=run.id)
    db_session.commit()

    db_session.refresh(run)
    assert run.status == TrainingRunStatus.COMPLETED.value
    assert run.error_message is None
    assert get_calls["n"] == 2

    versions = model_repository.list_all(db_session)
    assert len(versions) == 1
    assert versions[0].name == MODEL_NAME_UNET
    assert versions[0].prototypes is None

    evaluations = model_repository.list_evaluations(db_session, versions[0].id)
    assert len(evaluations) == 1
    assert evaluations[0].split == "TEST"
    assert evaluations[0].accuracy == pytest.approx(0.83)
    assert evaluations[0].metrics["best_epoch"] == 43
    assert evaluations[0].metrics["test"]["mean_dice_foreground"] == pytest.approx(0.83)


_CNN3D_CV_FIXTURE = {"k": 5, "mean_accuracy": 0.78, "std_accuracy": 0.05, "folds": [{"fold": 0, "accuracy": 0.8}]}
_CNN3D_FINAL_FIXTURE = {"best_val_accuracy": 0.81, "best_epoch": 40, "total_epochs": 60, "history": []}
_CNN3D_EXTERNAL_FIXTURE = {"test_patients": ["patient101"], "accuracy": 0.76, "validation": {"labels": ["NORMAL"], "sample_count": 1}}


def test_execute_dl_training_cnn3d_happy_path(db_session, tmp_path, monkeypatch):
    run = _make_dl_run(db_session, model_type=TrainingModelType.CNN3D_CLASSIFICATION.value)
    _patch_data_root(monkeypatch, tmp_path)

    cnn3d_dir = tmp_path / "models" / "cnn3d"
    cnn3d_dir.mkdir(parents=True)
    (cnn3d_dir / "cnn3d.pt").write_bytes(b"fake-weights")
    (cnn3d_dir / "cross_validation.json").write_text(json.dumps(_CNN3D_CV_FIXTURE))
    (cnn3d_dir / "final_model_training.json").write_text(json.dumps(_CNN3D_FINAL_FIXTURE))
    (cnn3d_dir / "external_test.json").write_text(json.dumps(_CNN3D_EXTERNAL_FIXTURE))

    monkeypatch.setattr(training_service.httpx, "post", lambda url, json=None, timeout=None: _FakeResponse({"job_id": "job-cnn3d-1"}))
    monkeypatch.setattr(
        training_service.httpx, "get",
        lambda url, timeout=None: _FakeResponse(
            {"status": "COMPLETED", "log_tail": "done", "result_path": "models/cnn3d", "error": None}
        ),
    )
    monkeypatch.setattr(training_service.time, "sleep", lambda s: None)

    training_service.execute_dl_training(db_session, training_run_id=run.id)
    db_session.commit()

    db_session.refresh(run)
    assert run.status == TrainingRunStatus.COMPLETED.value

    versions = model_repository.list_all(db_session)
    assert len(versions) == 1
    assert versions[0].name == MODEL_NAME_CNN3D

    evaluations = model_repository.list_evaluations(db_session, versions[0].id)
    assert evaluations[0].accuracy == pytest.approx(0.76)
    assert evaluations[0].metrics["cross_validation"]["mean_accuracy"] == pytest.approx(0.78)
    assert evaluations[0].metrics["final_model_training"]["best_epoch"] == 40
    assert evaluations[0].metrics["external_test"]["accuracy"] == pytest.approx(0.76)


def test_execute_dl_training_marks_run_failed_when_runner_reports_failed(db_session, tmp_path, monkeypatch):
    run = _make_dl_run(db_session, model_type=TrainingModelType.UNET_SEGMENTATION.value)
    _patch_data_root(monkeypatch, tmp_path)

    monkeypatch.setattr(training_service.httpx, "post", lambda url, json=None, timeout=None: _FakeResponse({"job_id": "job-x"}))
    monkeypatch.setattr(
        training_service.httpx, "get",
        lambda url, timeout=None: _FakeResponse(
            {"status": "FAILED", "log_tail": "CUDA out of memory", "result_path": None, "error": "GPU OOM"}
        ),
    )
    monkeypatch.setattr(training_service.time, "sleep", lambda s: None)

    training_service.execute_dl_training(db_session, training_run_id=run.id)
    db_session.commit()

    db_session.refresh(run)
    assert run.status == TrainingRunStatus.FAILED.value
    assert "GPU OOM" in run.error_message
    assert model_repository.list_all(db_session) == []


def test_execute_dl_training_marks_run_failed_when_runner_unreachable(db_session, tmp_path, monkeypatch):
    run = _make_dl_run(db_session, model_type=TrainingModelType.UNET_SEGMENTATION.value)
    _patch_data_root(monkeypatch, tmp_path)

    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("Connection refused")

    monkeypatch.setattr(training_service.httpx, "post", fake_post)

    training_service.execute_dl_training(db_session, training_run_id=run.id)
    db_session.commit()

    db_session.refresh(run)
    assert run.status == TrainingRunStatus.FAILED.value
    assert "ConnectError" in run.error_message or "Connection refused" in run.error_message


def test_execute_dl_training_times_out_instead_of_hanging(db_session, tmp_path, monkeypatch):
    run = _make_dl_run(db_session, model_type=TrainingModelType.UNET_SEGMENTATION.value)
    _patch_data_root(monkeypatch, tmp_path)

    monkeypatch.setattr(training_service.httpx, "post", lambda url, json=None, timeout=None: _FakeResponse({"job_id": "job-timeout"}))
    monkeypatch.setattr(training_service, "_DL_TIMEOUT_S", 1)

    # Jumps far ahead each call so the very first deadline check trips,
    # without needing a real ~90 minute wait for this test to prove the timeout path.
    counter = {"n": 0}

    def fake_monotonic():
        counter["n"] += 2
        return float(counter["n"])

    monkeypatch.setattr(training_service.time, "monotonic", fake_monotonic)

    training_service.execute_dl_training(db_session, training_run_id=run.id)
    db_session.commit()

    db_session.refresh(run)
    assert run.status == TrainingRunStatus.FAILED.value
    assert "did not finish within" in run.error_message
