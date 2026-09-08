"""Training pipeline: "smoke training" (see ml.cardiac_ai_ml.training) runs
eagerly in tests (see conftest.py's task_always_eager) against a real, local
file-backed MLflow tracking store (see conftest.py's MLFLOW_TRACKING_URI) —
so this genuinely exercises app.services.training_service's mlflow calls,
not a mock. Real server-backed tracking is verified separately inside Docker
Compose."""
import pytest

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
