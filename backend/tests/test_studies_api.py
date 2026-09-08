from tests.conftest import assign_doctor, make_patient, make_study, make_user


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_admin_creates_study_and_assigned_doctor_can_see_it(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin@cardiacai-test.dev", role="ADMIN")
    doctor = make_user(db_session, demo_org, email="doc@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-1")
    assign_doctor(db_session, patient=patient, doctor=doctor)

    admin_token = _login(client, "admin@cardiacai-test.dev")
    created = client.post(
        f"/api/v1/patients/{patient.id}/studies",
        headers=_auth(admin_token),
        json={"study_date": "2026-01-15", "modality": "Cardiac MRI"},
    )
    assert created.status_code == 201
    study_id = created.json()["id"]

    doctor_token = _login(client, "doc@cardiacai-test.dev")
    detail = client.get(f"/api/v1/studies/{study_id}", headers=_auth(doctor_token))
    assert detail.status_code == 200
    assert detail.json()["status"] == "PENDING"


def test_unassigned_doctor_cannot_reach_study(client, db_session, demo_org):
    make_user(db_session, demo_org, email="other@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-2")
    study = make_study(db_session, patient=patient)

    token = _login(client, "other@cardiacai-test.dev")
    response = client.get(f"/api/v1/studies/{study.id}", headers=_auth(token))
    assert response.status_code == 404


def test_doctor_can_mark_study_not_evaluable(client, db_session, demo_org):
    doctor = make_user(db_session, demo_org, email="doc4@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-3")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient, status="COMPLETED")

    token = _login(client, "doc4@cardiacai-test.dev")
    response = client.patch(
        f"/api/v1/studies/{study.id}", headers=_auth(token), json={"status": "NOT_EVALUABLE"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_EVALUABLE"


def test_review_history_is_append_only_not_overwritten(client, db_session, demo_org):
    doctor = make_user(db_session, demo_org, email="doc5@cardiacai-test.dev", role="DOCTOR")
    patient = make_patient(db_session, demo_org, identifier="PT-4")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    study = make_study(db_session, patient=patient)

    token = _login(client, "doc5@cardiacai-test.dev")

    first = client.post(
        f"/api/v1/studies/{study.id}/reviews",
        headers=_auth(token),
        json={"action": "REJECTED", "comment": "Looks wrong"},
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/studies/{study.id}/reviews",
        headers=_auth(token),
        json={"action": "CORRECTED", "corrected_diagnosis": "HCM", "comment": "Corrected after review"},
    )
    assert second.status_code == 201

    history = client.get(f"/api/v1/studies/{study.id}/reviews", headers=_auth(token))
    actions = [r["action"] for r in history.json()]
    # Both reviews must still be present — the second never overwrote the first.
    assert actions == ["CORRECTED", "REJECTED"]  # newest first


def test_admin_cannot_submit_a_clinical_review(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin9@cardiacai-test.dev", role="ADMIN")
    patient = make_patient(db_session, demo_org, identifier="PT-5")
    study = make_study(db_session, patient=patient)

    token = _login(client, "admin9@cardiacai-test.dev")
    response = client.post(
        f"/api/v1/studies/{study.id}/reviews",
        headers=_auth(token),
        json={"action": "ACCEPTED"},
    )
    assert response.status_code == 403
