"""Imaging/segmentation/biomarker API tests. MinIO is replaced by an
in-memory fake (see tests/conftest.py's `fake_storage`, autouse) so these run
without a real object store — the same in-memory-substitute pattern
conftest.py uses for Postgres via SQLite. Real end-to-end storage is verified
separately inside Docker Compose (see docs/architecture.md)."""
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from tests.conftest import assign_doctor, make_patient, make_study, make_user


def _nifti_bytes(array: np.ndarray, spacing: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> bytes:
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    image = nib.Nifti1Image(array.astype(np.int16), affine)
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        nib.save(image, tmp_path)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _setup_assigned_doctor(db_session, demo_org, *, patient_suffix: str):
    doctor = make_user(db_session, demo_org, email=f"doc-{patient_suffix}@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier=f"PT-IMG-{patient_suffix}")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    return doctor, study


def test_upload_series_extracts_voxel_spacing_and_shape(client, db_session, demo_org):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, patient_suffix="1")
    token = _login(client, "doc-1@cardiacai-test.dev")

    volume = np.zeros((10, 12, 8), dtype=np.int16)
    file_bytes = _nifti_bytes(volume, spacing=(1.5, 1.5, 8.0))

    response = client.post(
        f"/api/v1/studies/{study.id}/series",
        headers=_auth(token),
        files={"file": ("series.nii.gz", file_bytes, "application/octet-stream")},
        data={"series_type": "CINE_SHORT_AXIS", "phase": "ED"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["shape_x"] == 10 and body["shape_y"] == 12 and body["shape_z"] == 8
    assert body["voxel_spacing_x_mm"] == pytest.approx(1.5)
    assert body["voxel_spacing_z_mm"] == pytest.approx(8.0)
    assert body["phase"] == "ED"


def test_unassigned_doctor_cannot_upload_or_list_series(client, db_session, demo_org):
    make_user(db_session, demo_org, email="stranger@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-IMG-2")
    study = make_study(db_session, patient=patient)
    token = _login(client, "stranger@cardiacai-test.dev")

    response = client.get(f"/api/v1/studies/{study.id}/series", headers=_auth(token))
    assert response.status_code == 404


def test_upload_segmentation_computes_biomarkers(client, db_session, demo_org):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, patient_suffix="3")
    token = _login(client, "doc-3@cardiacai-test.dev")

    shape = (20, 20, 20)
    volume = np.zeros(shape, dtype=np.int16)
    series_response = client.post(
        f"/api/v1/studies/{study.id}/series",
        headers=_auth(token),
        files={"file": ("series.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
        data={"series_type": "CINE_SHORT_AXIS"},
    )
    series_id = series_response.json()["id"]

    mask = np.zeros(shape, dtype=np.int16)
    mask[2:6, 2:6, 2:6] = 3  # left_ventricle_cavity, 64 voxels -> 0.064 mL at 1mm spacing
    mask[10:14, 10:14, 10:14] = 2  # myocardium, 64 voxels

    seg_response = client.post(
        f"/api/v1/series/{series_id}/segmentations",
        headers=_auth(token),
        files={"file": ("mask.nii.gz", _nifti_bytes(mask), "application/octet-stream")},
    )

    assert seg_response.status_code == 201
    biomarkers = {m["name"]: m["value"] for m in seg_response.json()["biomarker_measurements"]}
    assert biomarkers["LV_VOLUME"] == pytest.approx(0.064)
    assert biomarkers["MYOCARDIAL_MASS"] == pytest.approx(0.064 * 1.05)

    listed = client.get(f"/api/v1/series/{series_id}/segmentations", headers=_auth(token))
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_upload_segmentation_rejects_shape_mismatch(client, db_session, demo_org):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, patient_suffix="4")
    token = _login(client, "doc-4@cardiacai-test.dev")

    series_response = client.post(
        f"/api/v1/studies/{study.id}/series",
        headers=_auth(token),
        files={"file": ("series.nii.gz", _nifti_bytes(np.zeros((10, 10, 10), dtype=np.int16)), "application/octet-stream")},
    )
    series_id = series_response.json()["id"]

    mismatched_mask = np.zeros((5, 5, 5), dtype=np.int16)
    response = client.post(
        f"/api/v1/series/{series_id}/segmentations",
        headers=_auth(token),
        files={"file": ("mask.nii.gz", _nifti_bytes(mismatched_mask), "application/octet-stream")},
    )

    assert response.status_code == 422


def test_series_and_segmentation_file_download_roundtrip(client, db_session, demo_org):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, patient_suffix="5")
    token = _login(client, "doc-5@cardiacai-test.dev")

    volume = np.arange(1000, dtype=np.int16).reshape((10, 10, 10))
    original_bytes = _nifti_bytes(volume)
    series_response = client.post(
        f"/api/v1/studies/{study.id}/series",
        headers=_auth(token),
        files={"file": ("series.nii.gz", original_bytes, "application/octet-stream")},
    )
    series_id = series_response.json()["id"]

    downloaded = client.get(f"/api/v1/series/{series_id}/file", headers=_auth(token))
    assert downloaded.status_code == 200
    assert downloaded.content == original_bytes


def test_invalid_nifti_upload_is_rejected(client, db_session, demo_org):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, patient_suffix="6")
    token = _login(client, "doc-6@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/studies/{study.id}/series",
        headers=_auth(token),
        files={"file": ("not-a-nifti.nii.gz", b"this is not a real nifti file", "application/octet-stream")},
    )
    assert response.status_code == 422
