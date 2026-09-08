"""Dataset versioning: only APPROVED annotations become cases, splits are
enforced at the patient level, and a LOCKED version is immutable and
checksummed — see docs/phases.md."""
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


def _make_approved_annotation(db_session, demo_org, *, patient_identifier: str, annotator):
    patient = make_patient(db_session, demo_org, identifier=patient_identifier)
    study = make_study(db_session, patient=patient)
    series = make_series(db_session, study=study, phase="ED")
    segmentation = make_segmentation_with_biomarkers(
        db_session, series=series,
        biomarkers={"LV_VOLUME": 100.0, "RV_VOLUME": 100.0, "MYOCARDIAL_VOLUME": 100.0, "MYOCARDIAL_MASS": 100.0},
    )
    return make_annotation(db_session, segmentation=segmentation, annotator=annotator, status="APPROVED")


def _create_dataset_and_version(client, token) -> tuple[str, str]:
    dataset = client.post("/api/v1/datasets", headers=_auth(token), json={"name": "ACDC demo"}).json()
    version = client.post(f"/api/v1/datasets/{dataset['id']}/versions", headers=_auth(token)).json()
    return dataset["id"], version["id"]


def test_ml_engineer_creates_dataset_and_version(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml1@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml1@cardiacai-test.dev")

    dataset = client.post("/api/v1/datasets", headers=_auth(token), json={"name": "Dataset A"})
    assert dataset.status_code == 201

    version = client.post(f"/api/v1/datasets/{dataset.json()['id']}/versions", headers=_auth(token))
    assert version.status_code == 201
    assert version.json()["version_number"] == 1
    assert version.json()["status"] == "DRAFT"


def test_add_case_and_lock_version_computes_checksum(client, db_session, demo_org):
    _engineer = make_user(db_session, demo_org, email="ml2@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email="annot-ml2@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, "ml2@cardiacai-test.dev")
    dataset_id, version_id = _create_dataset_and_version(client, token)

    annotation = _make_approved_annotation(db_session, demo_org, patient_identifier="PT-DS-1", annotator=annotator)

    added = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(annotation.id), "split": "TRAIN"},
    )
    assert added.status_code == 201
    assert added.json()["split"] == "TRAIN"

    locked = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/lock", headers=_auth(token))
    assert locked.status_code == 200
    assert locked.json()["status"] == "LOCKED"
    assert locked.json()["checksum"] is not None
    assert len(locked.json()["checksum"]) == 64  # sha256 hex digest


def test_unapproved_annotation_cannot_become_a_case(client, db_session, demo_org):
    _engineer = make_user(db_session, demo_org, email="ml3@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email="annot-ml3@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, "ml3@cardiacai-test.dev")
    dataset_id, version_id = _create_dataset_and_version(client, token)

    patient = make_patient(db_session, demo_org, identifier="PT-DS-3")
    study = make_study(db_session, patient=patient)
    series = make_series(db_session, study=study, phase="ED")
    segmentation = make_segmentation_with_biomarkers(
        db_session, series=series, biomarkers={"LV_VOLUME": 1.0, "RV_VOLUME": 1.0, "MYOCARDIAL_VOLUME": 1.0, "MYOCARDIAL_MASS": 1.0},
    )
    draft_annotation = make_annotation(db_session, segmentation=segmentation, annotator=annotator, status="DRAFT")

    response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(draft_annotation.id), "split": "TRAIN"},
    )
    assert response.status_code == 422


def test_cannot_add_case_to_locked_version(client, db_session, demo_org):
    _engineer = make_user(db_session, demo_org, email="ml4@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email="annot-ml4@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, "ml4@cardiacai-test.dev")
    dataset_id, version_id = _create_dataset_and_version(client, token)

    first_annotation = _make_approved_annotation(db_session, demo_org, patient_identifier="PT-DS-4a", annotator=annotator)
    client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(first_annotation.id), "split": "TRAIN"},
    )
    client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/lock", headers=_auth(token))

    second_annotation = _make_approved_annotation(db_session, demo_org, patient_identifier="PT-DS-4b", annotator=annotator)
    response = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(second_annotation.id), "split": "TRAIN"},
    )
    assert response.status_code == 409


def test_locking_empty_version_is_rejected(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml5@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml5@cardiacai-test.dev")
    dataset_id, version_id = _create_dataset_and_version(client, token)

    response = client.post(f"/api/v1/datasets/{dataset_id}/versions/{version_id}/lock", headers=_auth(token))
    assert response.status_code == 422


def test_patient_level_split_conflict_is_rejected(client, db_session, demo_org):
    """The same patient cannot have cases in two different splits within one
    dataset version — that would leak patient information across TRAIN/TEST."""
    _engineer = make_user(db_session, demo_org, email="ml6@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email="annot-ml6@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, "ml6@cardiacai-test.dev")
    dataset_id, version_id = _create_dataset_and_version(client, token)

    patient = make_patient(db_session, demo_org, identifier="PT-DS-6")
    study_1 = make_study(db_session, patient=patient, study_date="2026-01-01")
    series_1 = make_series(db_session, study=study_1, phase="ED")
    segmentation_1 = make_segmentation_with_biomarkers(
        db_session, series=series_1, biomarkers={"LV_VOLUME": 1.0, "RV_VOLUME": 1.0, "MYOCARDIAL_VOLUME": 1.0, "MYOCARDIAL_MASS": 1.0},
    )
    annotation_1 = make_annotation(db_session, segmentation=segmentation_1, annotator=annotator, status="APPROVED")

    study_2 = make_study(db_session, patient=patient, study_date="2026-02-01")
    series_2 = make_series(db_session, study=study_2, phase="ED")
    segmentation_2 = make_segmentation_with_biomarkers(
        db_session, series=series_2, biomarkers={"LV_VOLUME": 2.0, "RV_VOLUME": 2.0, "MYOCARDIAL_VOLUME": 2.0, "MYOCARDIAL_MASS": 2.0},
    )
    annotation_2 = make_annotation(db_session, segmentation=segmentation_2, annotator=annotator, status="APPROVED")

    first = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(annotation_1.id), "split": "TRAIN"},
    )
    assert first.status_code == 201

    conflicting = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(annotation_2.id), "split": "TEST"},
    )
    assert conflicting.status_code == 409


def test_same_patient_same_split_is_allowed(client, db_session, demo_org):
    _engineer = make_user(db_session, demo_org, email="ml7@cardiacai-test.dev", role="ML_ENGINEER")
    annotator = make_user(db_session, demo_org, email="annot-ml7@cardiacai-test.dev", role="ANNOTATOR")
    token = _login(client, "ml7@cardiacai-test.dev")
    dataset_id, version_id = _create_dataset_and_version(client, token)

    patient = make_patient(db_session, demo_org, identifier="PT-DS-7")
    study_1 = make_study(db_session, patient=patient, study_date="2026-01-01")
    series_1 = make_series(db_session, study=study_1, phase="ED")
    segmentation_1 = make_segmentation_with_biomarkers(
        db_session, series=series_1, biomarkers={"LV_VOLUME": 1.0, "RV_VOLUME": 1.0, "MYOCARDIAL_VOLUME": 1.0, "MYOCARDIAL_MASS": 1.0},
    )
    annotation_1 = make_annotation(db_session, segmentation=segmentation_1, annotator=annotator, status="APPROVED")

    study_2 = make_study(db_session, patient=patient, study_date="2026-02-01")
    series_2 = make_series(db_session, study=study_2, phase="ED")
    segmentation_2 = make_segmentation_with_biomarkers(
        db_session, series=series_2, biomarkers={"LV_VOLUME": 2.0, "RV_VOLUME": 2.0, "MYOCARDIAL_VOLUME": 2.0, "MYOCARDIAL_MASS": 2.0},
    )
    annotation_2 = make_annotation(db_session, segmentation=segmentation_2, annotator=annotator, status="APPROVED")

    client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(annotation_1.id), "split": "TRAIN"},
    )
    second = client.post(
        f"/api/v1/datasets/{dataset_id}/versions/{version_id}/cases",
        headers=_auth(token), json={"annotation_id": str(annotation_2.id), "split": "TRAIN"},
    )
    assert second.status_code == 201


def test_non_ml_engineer_cannot_access_datasets(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doc-ds@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc-ds@cardiacai-test.dev")

    response = client.get("/api/v1/datasets", headers=_auth(token))
    assert response.status_code == 403
