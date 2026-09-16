"""Real auto-segmentation (EPIC-2): POST /series/{id}/auto-segmentation runs
the production U-Net over an already-uploaded series and creates a real
`Segmentation` with real biomarkers computed from its predicted mask.

The actual GPU forward pass (app.services.dl_inference_client.segment_unet)
is monkeypatched here — no host runner/GPU in this test environment, same
approach test_training_api.py already uses for /jobs — but everything
downstream of that boundary (production-model lookup, biomarker computation
via the real cardiac_ai_ml.biomarkers.compute_frame_biomarkers, storage,
audit, RBAC) is genuinely exercised. The "runner truly unreachable" case is
exercised for real (no monkeypatch) in test_dl_inference_client.py.
"""
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.core.model_registry import MODEL_NAME_UNET
from app.services import auto_segmentation_service
from tests.conftest import assign_doctor, make_model_version, make_patient, make_study, make_user


def _setup_assigned_doctor(db_session, demo_org, *, email: str, patient_suffix: str):
    doctor = make_user(db_session, demo_org, email=email, role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier=f"PT-AUTO-{patient_suffix}")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    return doctor, study


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


def _upload_series(client, token, study_id, *, shape=(8, 8, 4)) -> str:
    volume = np.zeros(shape, dtype=np.int16)
    response = client.post(
        f"/api/v1/studies/{study_id}/series",
        headers=_auth(token),
        files={"file": ("series.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
        data={"series_type": "CINE_SHORT_AXIS", "phase": "ED"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def _fake_mask(shape=(6, 6, 3)) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.int32)
    mask[0:2, 0:2, :] = 3  # left ventricle cavity
    mask[3:5, 3:5, :] = 2  # myocardium
    return mask


def test_auto_segmentation_creates_real_biomarkers_from_the_predicted_mask(client, db_session, demo_org, monkeypatch):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, email="doc-auto1@cardiacai-test.dev", patient_suffix="1")
    make_model_version(db_session, name=MODEL_NAME_UNET, status="PRODUCTION")

    token = _login(client, "doc-auto1@cardiacai-test.dev")
    series_id = _upload_series(client, token, study.id)

    mask = _fake_mask()

    def fake_segment_unet(*, image_bytes: bytes):
        assert image_bytes  # the real series bytes were passed through
        return mask, 1.25, 1.25, 8.0

    monkeypatch.setattr(auto_segmentation_service.dl_inference_client, "segment_unet", fake_segment_unet)

    response = client.post(f"/api/v1/series/{series_id}/auto-segmentation", headers=_auth(token))
    assert response.status_code == 201
    body = response.json()
    assert body["model_version"].startswith(f"{MODEL_NAME_UNET}@")

    from cardiac_ai_ml.biomarkers import VoxelSpacing, compute_frame_biomarkers

    expected = compute_frame_biomarkers(mask, VoxelSpacing(x_mm=1.25, y_mm=1.25, z_mm=8.0))
    biomarkers = {m["name"]: m["value"] for m in body["biomarker_measurements"]}
    assert biomarkers["LV_VOLUME"] == pytest.approx(expected.lv_volume_ml)
    assert biomarkers["MYOCARDIAL_MASS"] == pytest.approx(expected.myocardial_mass_g)

    listed = client.get(f"/api/v1/series/{series_id}/segmentations", headers=_auth(token))
    assert listed.status_code == 200
    assert len(listed.json()) == 1


def test_auto_segmentation_without_a_production_unet_returns_409(client, db_session, demo_org):
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, email="doc-auto2@cardiacai-test.dev", patient_suffix="2")
    token = _login(client, "doc-auto2@cardiacai-test.dev")
    series_id = _upload_series(client, token, study.id)

    response = client.post(f"/api/v1/series/{series_id}/auto-segmentation", headers=_auth(token))
    assert response.status_code == 409


def test_auto_segmentation_fails_cleanly_when_the_runner_is_unreachable(client, db_session, demo_org, monkeypatch, tmp_path):
    """The HTTP call itself is not mocked — only the runner's URL is pointed
    at a real socket nothing listens on (127.0.0.1:1, a reserved/unassigned
    port — fails fast, unlike relying on whatever host.docker.internal
    happens to resolve to in this dev sandbox), so this exercises the real
    "manual prerequisite not met" failure mode end-to-end through the API."""
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "training_runner_url", "http://127.0.0.1:1")
    monkeypatch.setattr(get_settings(), "data_root", str(tmp_path))

    _doctor, study = _setup_assigned_doctor(db_session, demo_org, email="doc-auto3@cardiacai-test.dev", patient_suffix="3")
    make_model_version(db_session, name=MODEL_NAME_UNET, status="PRODUCTION")
    token = _login(client, "doc-auto3@cardiacai-test.dev")
    series_id = _upload_series(client, token, study.id)

    response = client.post(f"/api/v1/series/{series_id}/auto-segmentation", headers=_auth(token))
    assert response.status_code == 503


def test_unassigned_doctor_cannot_trigger_auto_segmentation(client, db_session, demo_org):
    make_user(db_session, demo_org, email="stranger-auto@cardiacai-test.dev", role="DOCTOR")
    _doctor, study = _setup_assigned_doctor(db_session, demo_org, email="doc-auto4@cardiacai-test.dev", patient_suffix="4")
    owner_token = _login(client, "doc-auto4@cardiacai-test.dev")
    series_id = _upload_series(client, owner_token, study.id)

    stranger_token = _login(client, "stranger-auto@cardiacai-test.dev")
    response = client.post(
        f"/api/v1/series/{series_id}/auto-segmentation", headers=_auth(stranger_token),
    )
    assert response.status_code == 404
