"""Annotation workflow: DOCTOR sends a segmentation for correction, the
assigned ANNOTATOR drafts/submits it, and a DOCTOR reviews it into ground
truth (or rejects it) — see docs/permissions.md."""
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np

from tests.conftest import (
    assign_doctor,
    make_patient,
    make_segmentation_with_biomarkers,
    make_series,
    make_study,
    make_user,
)


def _nifti_bytes_from_array(array):
    image = nib.Nifti1Image(array, np.eye(4))
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        nib.save(image, path)
        return path.read_bytes()
    finally:
        path.unlink(missing_ok=True)


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_case(db_session, demo_org, *, suffix: str):
    doctor = make_user(db_session, demo_org, email=f"doc-an{suffix}@cardiacai-test.dev", role="DOCTOR")
    annotator = make_user(db_session, demo_org, email=f"annot{suffix}@cardiacai-test.dev", role="ANNOTATOR")
    patient = make_patient(db_session, demo_org, identifier=f"PT-AN-{suffix}")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    series = make_series(db_session, study=study, phase="ED")
    segmentation = make_segmentation_with_biomarkers(
        db_session, series=series,
        biomarkers={"LV_VOLUME": 100.0, "RV_VOLUME": 100.0, "MYOCARDIAL_VOLUME": 100.0, "MYOCARDIAL_MASS": 100.0},
    )
    return doctor, annotator, patient, study, segmentation


def test_doctor_requests_annotation_and_annotator_drafts_and_submits(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="1")
    doctor_token = _login(client, "doc-an1@cardiacai-test.dev")

    created = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "DRAFT"
    annotation_id = created.json()["id"]

    annotator_token = _login(client, "annot1@cardiacai-test.dev")
    drafted = client.patch(
        f"/api/v1/annotations/{annotation_id}",
        headers=_auth(annotator_token), data={"diagnosis_label": "NORMAL"},
    )
    assert drafted.status_code == 200
    assert drafted.json()["diagnosis_label"] == "NORMAL"

    submitted = client.post(f"/api/v1/annotations/{annotation_id}/submit", headers=_auth(annotator_token))
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "SUBMITTED"


def test_doctor_approves_annotation_into_ground_truth(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="2")
    doctor_token = _login(client, "doc-an2@cardiacai-test.dev")
    annotator_token = _login(client, "annot2@cardiacai-test.dev")

    annotation_id = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    ).json()["id"]
    client.patch(f"/api/v1/annotations/{annotation_id}", headers=_auth(annotator_token), data={"diagnosis_label": "NORMAL"})
    client.post(f"/api/v1/annotations/{annotation_id}/submit", headers=_auth(annotator_token))

    reviewed = client.post(
        f"/api/v1/annotations/{annotation_id}/review",
        headers=_auth(doctor_token), json={"approve": True, "comment": "Looks right"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "APPROVED"
    assert reviewed.json()["review_comment"] == "Looks right"


def test_doctor_rejects_annotation_back_to_annotator(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="3")
    doctor_token = _login(client, "doc-an3@cardiacai-test.dev")
    annotator_token = _login(client, "annot3@cardiacai-test.dev")

    annotation_id = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    ).json()["id"]
    client.patch(f"/api/v1/annotations/{annotation_id}", headers=_auth(annotator_token), data={"diagnosis_label": "NORMAL"})
    client.post(f"/api/v1/annotations/{annotation_id}/submit", headers=_auth(annotator_token))

    rejected = client.post(
        f"/api/v1/annotations/{annotation_id}/review",
        headers=_auth(doctor_token), json={"approve": False, "comment": "Please recheck the apex"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"


def test_requesting_annotation_with_non_annotator_user_fails(client, db_session, demo_org):
    doctor, _annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="4")
    doctor_token = _login(client, "doc-an4@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(doctor.id)},
    )
    assert response.status_code == 400


def test_invalid_diagnosis_label_is_rejected(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="5")
    doctor_token = _login(client, "doc-an5@cardiacai-test.dev")
    annotator_token = _login(client, "annot5@cardiacai-test.dev")

    annotation_id = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    ).json()["id"]

    response = client.patch(
        f"/api/v1/annotations/{annotation_id}", headers=_auth(annotator_token), data={"diagnosis_label": "NOT_A_REAL_CLASS"},
    )
    assert response.status_code == 422


def test_submitting_empty_draft_is_rejected(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="6")
    doctor_token = _login(client, "doc-an6@cardiacai-test.dev")
    annotator_token = _login(client, "annot6@cardiacai-test.dev")

    annotation_id = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    ).json()["id"]

    response = client.post(f"/api/v1/annotations/{annotation_id}/submit", headers=_auth(annotator_token))
    assert response.status_code == 409


def test_a_different_annotator_cannot_see_or_edit_someone_elses_case(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="7")
    make_user(db_session, demo_org, email="other-annot7@cardiacai-test.dev", role="ANNOTATOR")
    doctor_token = _login(client, "doc-an7@cardiacai-test.dev")
    other_annotator_token = _login(client, "other-annot7@cardiacai-test.dev")

    annotation_id = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    ).json()["id"]

    response = client.get(f"/api/v1/annotations/{annotation_id}", headers=_auth(other_annotator_token))
    assert response.status_code == 404

    patch_response = client.patch(
        f"/api/v1/annotations/{annotation_id}", headers=_auth(other_annotator_token), data={"diagnosis_label": "NORMAL"},
    )
    assert patch_response.status_code == 404


def test_unassigned_doctor_cannot_request_or_review_annotation(client, db_session, demo_org):
    _doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="8")
    make_user(db_session, demo_org, email="stranger-doc8@cardiacai-test.dev", role="DOCTOR")
    stranger_token = _login(client, "stranger-doc8@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(stranger_token), json={"annotator_user_id": str(annotator.id)},
    )
    assert response.status_code == 404


def test_uploading_corrected_mask_creates_a_new_segmentation_with_biomarkers(client, db_session, demo_org):
    doctor, annotator, _patient, _study, segmentation = _setup_case(db_session, demo_org, suffix="9")
    doctor_token = _login(client, "doc-an9@cardiacai-test.dev")
    annotator_token = _login(client, "annot9@cardiacai-test.dev")

    annotation_id = client.post(
        f"/api/v1/segmentations/{segmentation.id}/annotations",
        headers=_auth(doctor_token), json={"annotator_user_id": str(annotator.id)},
    ).json()["id"]

    mask = np.zeros((10, 10, 10), dtype=np.int16)
    mask[0:3, 0:3, 0:3] = 3  # LV cavity
    corrected_bytes = _nifti_bytes_from_array(mask)

    drafted = client.patch(
        f"/api/v1/annotations/{annotation_id}", headers=_auth(annotator_token),
        files={"file": ("corrected.nii.gz", corrected_bytes, "application/octet-stream")},
    )
    assert drafted.status_code == 200
    assert drafted.json()["corrected_segmentation_id"] is not None
    assert drafted.json()["corrected_segmentation_id"] != str(segmentation.id)
