"""AI analysis API tests. Celery runs eagerly (see conftest.py), so a
request to trigger an analysis completes synchronously within the same test
— no real Redis/worker needed. Real async execution against a live worker is
verified separately inside Docker Compose."""
import io
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
import pytest

from app.core.model_registry import MODEL_NAME_CNN3D, MODEL_NAME_UNET
from app.services import analysis_service, llm_explanation_service
from tests.conftest import (
    assign_doctor,
    make_model_version,
    make_patient,
    make_segmentation_with_biomarkers,
    make_series,
    make_study,
    make_user,
)


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


def _setup_study_with_ed_es(db_session, demo_org, *, suffix: str, es_lv_volume: float = 50.0):
    doctor = make_user(db_session, demo_org, email=f"doc-a{suffix}@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier=f"PT-A-{suffix}")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)

    ed_series = make_series(db_session, study=study, phase="ED")
    make_segmentation_with_biomarkers(
        db_session, series=ed_series,
        biomarkers={"LV_VOLUME": 140.0, "RV_VOLUME": 140.0, "MYOCARDIAL_VOLUME": 114.3, "MYOCARDIAL_MASS": 120.0},
    )
    es_series = make_series(db_session, study=study, phase="ES")
    make_segmentation_with_biomarkers(
        db_session, series=es_series,
        biomarkers={"LV_VOLUME": es_lv_volume, "RV_VOLUME": 60.0, "MYOCARDIAL_VOLUME": 114.3, "MYOCARDIAL_MASS": 120.0},
    )
    return doctor, study


def test_request_analysis_completes_synchronously_and_classifies(client, db_session, demo_org):
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="1", es_lv_volume=50.0)
    token = _login(client, "doc-a1@cardiacai-test.dev")

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    assert created.status_code == 202
    assert created.json()["status"] == "QUEUED"
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token))
    assert result.status_code == 200
    body = result.json()
    assert body["status"] == "COMPLETED"
    assert body["predicted_class"] == "NORMAL"
    assert body["probabilities"] is not None
    assert sum(body["probabilities"].values()) == pytest.approx(1.0)
    assert body["confidence"] == pytest.approx(max(body["probabilities"].values()))
    assert set(body["feature_attributions"]) == {"EJECTION_FRACTION", "LV_EDV", "RV_EDV", "LV_MASS"}
    assert body["features"]["EJECTION_FRACTION"] == pytest.approx((140.0 - 50.0) / 140.0 * 100.0)


def test_dilated_cardiomyopathy_profile_is_classified_accordingly(client, db_session, demo_org):
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="2", es_lv_volume=200.0)
    token = _login(client, "doc-a2@cardiacai-test.dev")

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token))
    # EDV 140, ESV 200 is impossible physiologically but drives EF sharply negative,
    # which is enough to move the classification away from NORMAL — this test only
    # cares that the pipeline actually reacts to the input, not clinical realism.
    assert result.json()["predicted_class"] != "NORMAL"


def test_list_analyses_for_study(client, db_session, demo_org):
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="3")
    token = _login(client, "doc-a3@cardiacai-test.dev")

    client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))

    listed = client.get(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    assert listed.status_code == 200
    assert len(listed.json()) == 2


def test_analysis_fails_gracefully_without_es_series(client, db_session, demo_org):
    doctor = make_user(db_session, demo_org, email="doc-a4@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-A-4")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    ed_series = make_series(db_session, study=study, phase="ED")
    make_segmentation_with_biomarkers(
        db_session, series=ed_series,
        biomarkers={"LV_VOLUME": 140.0, "RV_VOLUME": 140.0, "MYOCARDIAL_VOLUME": 114.3, "MYOCARDIAL_MASS": 120.0},
    )

    token = _login(client, "doc-a4@cardiacai-test.dev")
    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token))
    body = result.json()
    assert body["status"] == "FAILED"
    assert body["predicted_class"] is None
    assert "ED and an ES" in body["error_message"]


def test_unassigned_doctor_cannot_request_or_view_analysis(client, db_session, demo_org):
    make_user(db_session, demo_org, email="stranger-a@cardiacai-test.dev", role="DOCTOR")
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="5")
    token = _login(client, "stranger-a@cardiacai-test.dev")

    response = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    assert response.status_code == 404

    listed = client.get(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    assert listed.status_code == 404


def test_analysis_uses_the_production_model_when_one_exists(client, db_session, demo_org):
    """The Phase 7 "full circle": once a trained model is promoted to
    production, live inference switches from the demo heuristic to it
    automatically (see app.services.analysis_service.execute_analysis)."""
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="6", es_lv_volume=50.0)
    token = _login(client, "doc-a6@cardiacai-test.dev")

    # A production model whose HYPERTROPHIC_CARDIOMYOPATHY prototype exactly
    # matches this study's features — the demo heuristic would call this
    # NORMAL (see test_request_analysis_completes_synchronously_and_classifies),
    # so a different prediction proves the production model was actually used.
    features = {
        "EJECTION_FRACTION": (140.0 - 50.0) / 140.0 * 100.0,
        "LV_EDV": 140.0,
        "RV_EDV": 140.0,
        "LV_MASS": 120.0,
    }
    from cardiac_ai_ml.classification import DiagnosisClass, FEATURE_NAMES

    prototypes = {d.value: dict.fromkeys(FEATURE_NAMES, 9999.0) for d in DiagnosisClass}
    prototypes[DiagnosisClass.HYPERTROPHIC_CARDIOMYOPATHY.value] = features
    model_version = make_model_version(db_session, status="PRODUCTION", prototypes=prototypes)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["predicted_class"] == "HYPERTROPHIC_CARDIOMYOPATHY"
    assert str(model_version.id) in result["model_version"]


def test_cnn3d_production_model_serves_a_real_image_classification(client, db_session, demo_org, monkeypatch):
    """EPIC-2 refinement: when the PRODUCTION model is CNN3D_CLASSIFICATION,
    execute_analysis runs the real image-native forward pass (mocked at the
    host-runner HTTP boundary here — see test_dl_inference_client.py for the
    real, unmocked "runner unreachable" case) instead of the tabular
    nearest-centroid path — no segmentation-derived biomarkers needed at
    all, and feature_attributions stays honestly null (no tabular feature
    vector exists for an image-native model)."""
    doctor = make_user(db_session, demo_org, email="doc-cnn3d@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-CNN3D-1")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    token = _login(client, "doc-cnn3d@cardiacai-test.dev")

    volume = np.zeros((6, 6, 3), dtype=np.int16)
    for phase in ("ED", "ES"):
        upload = client.post(
            f"/api/v1/studies/{study.id}/series",
            headers=_auth(token),
            files={"file": (f"{phase}.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
            data={"series_type": "CINE_SHORT_AXIS", "phase": phase},
        )
        assert upload.status_code == 201

    model_version = make_model_version(db_session, name=MODEL_NAME_CNN3D, status="PRODUCTION")

    canned_prediction = {
        "predicted_class": "DILATED_CARDIOMYOPATHY",
        "probabilities": {
            "NORMAL": 0.05, "DILATED_CARDIOMYOPATHY": 0.7, "HYPERTROPHIC_CARDIOMYOPATHY": 0.1,
            "MYOCARDIAL_INFARCTION": 0.1, "ABNORMAL_RIGHT_VENTRICLE": 0.05,
        },
    }

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        assert ed_bytes  # the real uploaded series bytes were passed through
        assert es_bytes
        return canned_prediction

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["predicted_class"] == "DILATED_CARDIOMYOPATHY"
    assert result["probabilities"] == canned_prediction["probabilities"]
    assert result["confidence"] == pytest.approx(0.7)
    assert result["features"] is None
    assert result["feature_attributions"] is None
    assert str(model_version.id) in result["model_version"]


def test_cnn3d_inference_failure_marks_the_analysis_failed_not_crashed(client, db_session, demo_org, monkeypatch):
    doctor = make_user(db_session, demo_org, email="doc-cnn3d-fail@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-CNN3D-2")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    token = _login(client, "doc-cnn3d-fail@cardiacai-test.dev")

    volume = np.zeros((6, 6, 3), dtype=np.int16)
    for phase in ("ED", "ES"):
        client.post(
            f"/api/v1/studies/{study.id}/series",
            headers=_auth(token),
            files={"file": (f"{phase}.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
            data={"series_type": "CINE_SHORT_AXIS", "phase": phase},
        )
    make_model_version(db_session, name=MODEL_NAME_CNN3D, status="PRODUCTION")

    from app.services.dl_inference_client import InferenceRunnerError

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        raise InferenceRunnerError("host GPU runner is not running")

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "FAILED"
    assert "host GPU runner" in result["error_message"]


def _setup_cnn3d_study(client, db_session, demo_org, token: str, study):
    volume = np.zeros((6, 6, 3), dtype=np.int16)
    for phase in ("ED", "ES"):
        upload = client.post(
            f"/api/v1/studies/{study.id}/series",
            headers=_auth(token),
            files={"file": (f"{phase}.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
            data={"series_type": "CINE_SHORT_AXIS", "phase": phase},
        )
        assert upload.status_code == 201
    make_model_version(db_session, name=MODEL_NAME_CNN3D, status="PRODUCTION")


def test_analysis_persists_and_serves_gradcam_attribution_map(client, db_session, demo_org, monkeypatch):
    """EPIC-3: the runner's classify response can include a Grad-CAM
    attribution array alongside the classification — execute_analysis
    persists it to object storage and GET /analyses/{id}/gradcam serves the
    exact same array back."""
    doctor = make_user(db_session, demo_org, email="doc-gradcam-1@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-GRADCAM-1")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    token = _login(client, "doc-gradcam-1@cardiacai-test.dev")
    _setup_cnn3d_study(client, db_session, demo_org, token, study)

    attribution = np.random.default_rng(0).random((4, 4, 2)).astype(np.float32)

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        return {
            "predicted_class": "DILATED_CARDIOMYOPATHY",
            "probabilities": {
                "NORMAL": 0.1, "DILATED_CARDIOMYOPATHY": 0.6, "HYPERTROPHIC_CARDIOMYOPATHY": 0.1,
                "MYOCARDIAL_INFARCTION": 0.1, "ABNORMAL_RIGHT_VENTRICLE": 0.1,
            },
            "gradcam_attribution": attribution,
            "gradcam_layer_name": "features.3.2",
            "gradcam_error": None,
        }

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["gradcam_available"] is True
    assert result["gradcam_error"] is None

    gradcam_response = client.get(f"/api/v1/analyses/{analysis_id}/gradcam", headers=_auth(token))
    assert gradcam_response.status_code == 200
    assert gradcam_response.headers["content-type"] == "application/octet-stream"
    decoded = np.load(io.BytesIO(gradcam_response.content))
    np.testing.assert_allclose(decoded, attribution)


def test_analysis_completes_and_reports_honest_gradcam_error_when_gradcam_fails(
    client, db_session, demo_org, monkeypatch
):
    """A Grad-CAM-only failure never fails the whole analysis (contract point
    4) — the classification is COMPLETED, gradcam_available is False, and the
    gradcam endpoint responds honestly (404) instead of a fake empty 200."""
    doctor = make_user(db_session, demo_org, email="doc-gradcam-2@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-GRADCAM-2")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    token = _login(client, "doc-gradcam-2@cardiacai-test.dev")
    _setup_cnn3d_study(client, db_session, demo_org, token, study)

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        return {
            "predicted_class": "NORMAL",
            "probabilities": {"NORMAL": 1.0},
            "gradcam_attribution": None,
            "gradcam_layer_name": None,
            "gradcam_error": "gradient hook produced all-zero activations",
        }

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["gradcam_available"] is False
    assert "gradient hook produced all-zero activations" in result["gradcam_error"]

    gradcam_response = client.get(f"/api/v1/analyses/{analysis_id}/gradcam", headers=_auth(token))
    assert gradcam_response.status_code == 404
    assert "gradient hook produced all-zero activations" in gradcam_response.json()["detail"]


def test_analysis_without_gradcam_reports_honest_404_not_fake_success(client, db_session, demo_org):
    """The tabular nearest-centroid path never computes Grad-CAM at all — no
    fake 200, and no misleading gradcam_error (nothing failed, it's just not
    applicable to this model type)."""
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="gradcam3")
    token = _login(client, "doc-agradcam3@cardiacai-test.dev")

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["gradcam_available"] is False
    assert result["gradcam_error"] is None

    gradcam_response = client.get(f"/api/v1/analyses/{analysis_id}/gradcam", headers=_auth(token))
    assert gradcam_response.status_code == 404


def test_unassigned_doctor_cannot_fetch_gradcam_for_someone_elses_analysis(
    client, db_session, demo_org, monkeypatch
):
    make_user(db_session, demo_org, email="stranger-gradcam@cardiacai-test.dev", role="DOCTOR")
    doctor = make_user(db_session, demo_org, email="doc-gradcam-4@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-GRADCAM-4")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    owner_token = _login(client, "doc-gradcam-4@cardiacai-test.dev")
    _setup_cnn3d_study(client, db_session, demo_org, owner_token, study)

    attribution = np.zeros((2, 2, 2), dtype=np.float32)

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        return {
            "predicted_class": "NORMAL",
            "probabilities": {"NORMAL": 1.0},
            "gradcam_attribution": attribution,
            "gradcam_layer_name": "features.3.2",
            "gradcam_error": None,
        }

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(owner_token))
    analysis_id = created.json()["id"]

    stranger_token = _login(client, "stranger-gradcam@cardiacai-test.dev")
    response = client.get(f"/api/v1/analyses/{analysis_id}/gradcam", headers=_auth(stranger_token))
    assert response.status_code == 404


def _fake_unet_mask(lv_label_slice) -> np.ndarray:
    """Same label convention as test_auto_segmentation_api.py's _fake_mask:
    label 3 = LV cavity, label 2 = myocardium. `lv_label_slice` varies the
    LV cavity's extent between ED/ES calls so the derived EJECTION_FRACTION
    isn't degenerately zero."""
    mask = np.zeros((6, 6, 3), dtype=np.int32)
    mask[lv_label_slice, lv_label_slice, :] = 3
    mask[3:5, 3:5, :] = 2
    return mask


def test_cnn3d_analysis_also_persists_biomarker_consistency_from_auto_segmented_ed_es(
    client, db_session, demo_org, monkeypatch
):
    """EPIC-12: on top of the classification itself and Grad-CAM (EPIC-3), a
    real CNN3D analysis also auto-segments the ED and ES series (reusing
    auto_segmentation_service.generate_auto_segmentation, real Segmentation
    rows), derives biomarkers from them, and compares those biomarkers
    against the (demo, here — no nearest-centroid PRODUCTION model
    registered) prototypes for the class CNN3D predicted."""
    doctor = make_user(db_session, demo_org, email="doc-biocons-1@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-BIOCONS-1")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    token = _login(client, "doc-biocons-1@cardiacai-test.dev")

    volume = np.zeros((6, 6, 3), dtype=np.int16)
    series_ids = {}
    for phase in ("ED", "ES"):
        upload = client.post(
            f"/api/v1/studies/{study.id}/series",
            headers=_auth(token),
            files={"file": (f"{phase}.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
            data={"series_type": "CINE_SHORT_AXIS", "phase": phase},
        )
        assert upload.status_code == 201
        series_ids[phase] = upload.json()["id"]

    make_model_version(db_session, name=MODEL_NAME_CNN3D, status="PRODUCTION")
    make_model_version(db_session, name=MODEL_NAME_UNET, status="PRODUCTION")

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        return {
            "predicted_class": "DILATED_CARDIOMYOPATHY",
            "probabilities": {
                "NORMAL": 0.05, "DILATED_CARDIOMYOPATHY": 0.7, "HYPERTROPHIC_CARDIOMYOPATHY": 0.1,
                "MYOCARDIAL_INFARCTION": 0.1, "ABNORMAL_RIGHT_VENTRICLE": 0.05,
            },
        }

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    masks = iter([_fake_unet_mask(slice(0, 4)), _fake_unet_mask(slice(0, 2))])  # ED (bigger LV), then ES (smaller)

    def fake_segment_unet(*, image_bytes: bytes):
        assert image_bytes
        return next(masks), 1.0, 1.0, 1.0

    monkeypatch.setattr(analysis_service.auto_segmentation_service.dl_inference_client, "segment_unet", fake_segment_unet)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["predicted_class"] == "DILATED_CARDIOMYOPATHY"

    consistency = result["biomarker_consistency"]
    assert result["biomarker_consistency_error"] is None
    assert consistency is not None
    assert consistency["predicted_class"] == "DILATED_CARDIOMYOPATHY"
    assert consistency["reference_source"] == analysis_service.DEMO_MODEL_VERSION
    assert {pf["feature"] for pf in consistency["per_feature"]} == {
        "EJECTION_FRACTION", "LV_EDV", "RV_EDV", "LV_MASS",
    }
    assert set(consistency["distance_to_each_class"]) == {
        "NORMAL", "DILATED_CARDIOMYOPATHY", "HYPERTROPHIC_CARDIOMYOPATHY",
        "MYOCARDIAL_INFARCTION", "ABNORMAL_RIGHT_VENTRICLE",
    }

    # Real Segmentation rows were created for both ED and ES — not an
    # ephemeral/discarded computation (EPIC-12's "Contrato técnico" point 2).
    for phase in ("ED", "ES"):
        segmentations = client.get(
            f"/api/v1/series/{series_ids[phase]}/segmentations", headers=_auth(token)
        ).json()
        assert len(segmentations) == 1
        assert segmentations[0]["model_version"].startswith(f"{MODEL_NAME_UNET}@")


def test_cnn3d_analysis_stays_completed_when_biomarker_consistency_fails(
    client, db_session, demo_org, monkeypatch
):
    """EPIC-12 point 5: no U-Net PRODUCTION model registered means the
    auto-segmentation this signal depends on can't run — the CNN3D
    classification itself already succeeded and must stay COMPLETED, with an
    honest biomarker_consistency_error instead of biomarker_consistency."""
    doctor = make_user(db_session, demo_org, email="doc-biocons-2@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-BIOCONS-2")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)
    token = _login(client, "doc-biocons-2@cardiacai-test.dev")

    volume = np.zeros((6, 6, 3), dtype=np.int16)
    for phase in ("ED", "ES"):
        upload = client.post(
            f"/api/v1/studies/{study.id}/series",
            headers=_auth(token),
            files={"file": (f"{phase}.nii.gz", _nifti_bytes(volume), "application/octet-stream")},
            data={"series_type": "CINE_SHORT_AXIS", "phase": phase},
        )
        assert upload.status_code == 201

    make_model_version(db_session, name=MODEL_NAME_CNN3D, status="PRODUCTION")
    # Deliberately no "cardiac-segmentation-unet" PRODUCTION model.

    def fake_classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes):
        return {
            "predicted_class": "NORMAL",
            "probabilities": {"NORMAL": 0.9, "DILATED_CARDIOMYOPATHY": 0.1},
        }

    monkeypatch.setattr(analysis_service.dl_inference_client, "classify_cnn3d", fake_classify_cnn3d)

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["status"] == "COMPLETED"
    assert result["predicted_class"] == "NORMAL"
    assert result["biomarker_consistency"] is None
    assert result["biomarker_consistency_error"] is not None
    assert "Consistencia de biomarcadores no disponible" in result["biomarker_consistency_error"]


class _FakeOllamaResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def test_generate_explanation_calls_ollama_for_real_and_caches_it(client, db_session, demo_org, monkeypatch):
    """EPIC-18: the first call with no cached explanation hits Ollama for
    real (httpx is monkeypatched, same approach as
    test_dl_inference_client.py — no real Ollama in the test environment)
    and persists the result; a second call without `force` returns the
    cached text without calling Ollama again."""
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="llm1", es_lv_volume=50.0)
    token = _login(client, "doc-allm1@cardiacai-test.dev")

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    call_count = {"n": 0}
    seen_payload = {}

    def fake_post(url, json=None, timeout=None):
        call_count["n"] += 1
        seen_payload.update(json)
        return _FakeOllamaResponse({"response": "El modelo predice NORMAL con alta confianza.", "done": True})

    monkeypatch.setattr(llm_explanation_service.httpx, "post", fake_post)

    first = client.post(f"/api/v1/analyses/{analysis_id}/explanation", headers=_auth(token))
    assert first.status_code == 200
    assert first.json() == {"explanation": "El modelo predice NORMAL con alta confianza.", "error": None}
    assert call_count["n"] == 1
    assert "NORMAL" in seen_payload["prompt"]
    assert seen_payload["stream"] is False

    second = client.post(f"/api/v1/analyses/{analysis_id}/explanation", headers=_auth(token))
    assert second.status_code == 200
    assert second.json()["explanation"] == "El modelo predice NORMAL con alta confianza."
    assert call_count["n"] == 1  # cached — Ollama not called again

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["llm_explanation_available"] is True
    assert result["llm_explanation_error"] is None


def test_generate_explanation_switches_language_without_force(client, db_session, demo_org, monkeypatch):
    """EPIC-18 follow-up: the UI's language toggle should invalidate the
    cache the same way force=true does — a clinician switching from English
    to Spanish must never see a stale-language cached explanation reused."""
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="llmlang", es_lv_volume=50.0)
    token = _login(client, "doc-allmlang@cardiacai-test.dev")
    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    seen_systems = []

    def fake_post(url, json=None, timeout=None):
        seen_systems.append(json["system"])
        text = "In English." if "in English" in json["system"] else "En español."
        return _FakeOllamaResponse({"response": text, "done": True})

    monkeypatch.setattr(llm_explanation_service.httpx, "post", fake_post)

    en_response = client.post(f"/api/v1/analyses/{analysis_id}/explanation?language=en", headers=_auth(token))
    assert en_response.json()["explanation"] == "In English."

    es_response = client.post(f"/api/v1/analyses/{analysis_id}/explanation?language=es", headers=_auth(token))
    assert es_response.json()["explanation"] == "En español."
    assert len(seen_systems) == 2  # switching language triggered a real second call, not a cache hit

    # Switching back to English without force must not need a third real
    # call — it's cached again... except the cache only holds the *last*
    # language, so this is a genuine regeneration too (documented tradeoff:
    # one slot, not one per language).
    en_again = client.post(f"/api/v1/analyses/{analysis_id}/explanation?language=en", headers=_auth(token))
    assert en_again.json()["explanation"] == "In English."
    assert len(seen_systems) == 3

    # Repeating the same language again *is* a real cache hit.
    en_cached = client.post(f"/api/v1/analyses/{analysis_id}/explanation?language=en", headers=_auth(token))
    assert en_cached.json()["explanation"] == "In English."
    assert len(seen_systems) == 3


def test_generate_explanation_force_regenerates(client, db_session, demo_org, monkeypatch):
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="llm2", es_lv_volume=50.0)
    token = _login(client, "doc-allm2@cardiacai-test.dev")
    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    responses = iter(["primera versión", "segunda versión"])

    def fake_post(url, json=None, timeout=None):
        return _FakeOllamaResponse({"response": next(responses), "done": True})

    monkeypatch.setattr(llm_explanation_service.httpx, "post", fake_post)

    first = client.post(f"/api/v1/analyses/{analysis_id}/explanation", headers=_auth(token))
    assert first.json()["explanation"] == "primera versión"

    regenerated = client.post(f"/api/v1/analyses/{analysis_id}/explanation?force=true", headers=_auth(token))
    assert regenerated.json()["explanation"] == "segunda versión"


def test_generate_explanation_reports_honest_error_when_ollama_unreachable(client, db_session, demo_org):
    """No monkeypatch at all — Ollama is genuinely unreachable in the test
    environment, so this exercises the real connection-error path, not a
    simulated one. Contract: 200 with an honest `error` field, never a
    fabricated explanation and never a raised exception."""
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="llm3", es_lv_volume=50.0)
    token = _login(client, "doc-allm3@cardiacai-test.dev")
    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(token))
    analysis_id = created.json()["id"]

    response = client.post(f"/api/v1/analyses/{analysis_id}/explanation", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] is None
    assert body["error"] is not None

    result = client.get(f"/api/v1/analyses/{analysis_id}", headers=_auth(token)).json()
    assert result["llm_explanation_available"] is False
    assert "Ollama" in result["llm_explanation_error"]


def test_unassigned_doctor_cannot_generate_explanation_for_someone_elses_analysis(client, db_session, demo_org):
    make_user(db_session, demo_org, email="stranger-llm@cardiacai-test.dev", role="DOCTOR")
    _doctor, study = _setup_study_with_ed_es(db_session, demo_org, suffix="llm4", es_lv_volume=50.0)
    owner_token = _login(client, "doc-allm4@cardiacai-test.dev")

    created = client.post(f"/api/v1/studies/{study.id}/analyses", headers=_auth(owner_token))
    analysis_id = created.json()["id"]

    stranger_token = _login(client, "stranger-llm@cardiacai-test.dev")
    response = client.post(f"/api/v1/analyses/{analysis_id}/explanation", headers=_auth(stranger_token))
    assert response.status_code == 404
