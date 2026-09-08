"""AI analysis API tests. Celery runs eagerly (see conftest.py), so a
request to trigger an analysis completes synchronously within the same test
— no real Redis/worker needed. Real async execution against a live worker is
verified separately inside Docker Compose."""
import pytest

from tests.conftest import (
    assign_doctor,
    make_model_version,
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
