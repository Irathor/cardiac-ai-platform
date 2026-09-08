"""Patients screen: pagination, search, sort, filters, and — most
importantly — that a DOCTOR can never see a patient they aren't assigned to,
even by crafting the request directly (see docs/permissions.md)."""
import pytest

from tests.conftest import assign_doctor, make_ai_analysis, make_patient, make_study, make_user


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_create_and_list_patients(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin@cardiacai-test.dev", role="ADMIN")
    token = _login(client, "admin@cardiacai-test.dev")

    created = client.post(
        "/api/v1/patients",
        headers=_auth(token),
        json={
            "identifier": "PT-0001",
            "first_name": "Ana",
            "last_name": "Alonso",
            "date_of_birth": "1990-05-01",
        },
    )
    assert created.status_code == 201

    listing = client.get("/api/v1/patients", headers=_auth(token))
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["identifier"] == "PT-0001"


def test_doctor_only_sees_assigned_patients_even_with_manipulated_query(
    client, db_session, demo_org
):
    doctor = make_user(db_session, demo_org, email="doc@cardiacai-test.dev", role="DOCTOR")
    other_doctor = make_user(db_session, demo_org, email="doc2@cardiacai-test.dev", role="DOCTOR")

    assigned_patient = make_patient(db_session, demo_org, identifier="PT-A", last_name="Alonso")
    other_patient = make_patient(db_session, demo_org, identifier="PT-B", last_name="Beltran")
    assign_doctor(db_session, patient=assigned_patient, doctor=doctor)
    assign_doctor(db_session, patient=other_patient, doctor=other_doctor)

    token = _login(client, "doc@cardiacai-test.dev")

    listing = client.get("/api/v1/patients", headers=_auth(token))
    identifiers = {item["identifier"] for item in listing.json()["items"]}
    assert identifiers == {"PT-A"}

    # Manipulated query params must not widen access.
    listing_wide = client.get(
        "/api/v1/patients", headers=_auth(token), params={"page_size": 200, "only_mine": "false"}
    )
    identifiers_wide = {item["identifier"] for item in listing_wide.json()["items"]}
    assert identifiers_wide == {"PT-A"}

    # Direct detail access to someone else's assigned patient -> 404, not 403
    # (never confirm the other patient's existence to this doctor).
    detail = client.get(f"/api/v1/patients/{other_patient.id}", headers=_auth(token))
    assert detail.status_code == 404

    own_detail = client.get(f"/api/v1/patients/{assigned_patient.id}", headers=_auth(token))
    assert own_detail.status_code == 200


def test_admin_sees_all_patients_regardless_of_assignment(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin2@cardiacai-test.dev", role="ADMIN")
    make_patient(db_session, demo_org, identifier="PT-X", last_name="Xu")
    make_patient(db_session, demo_org, identifier="PT-Y", last_name="Yang")

    token = _login(client, "admin2@cardiacai-test.dev")
    listing = client.get("/api/v1/patients", headers=_auth(token))
    assert listing.json()["total"] == 2


def test_search_filters_by_name_or_identifier(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin3@cardiacai-test.dev", role="ADMIN")
    make_patient(db_session, demo_org, identifier="PT-0010", first_name="Carlos", last_name="Ruiz")
    make_patient(db_session, demo_org, identifier="PT-0020", first_name="Marta", last_name="Diaz")

    token = _login(client, "admin3@cardiacai-test.dev")
    by_name = client.get("/api/v1/patients", headers=_auth(token), params={"search": "ruiz"})
    assert [i["identifier"] for i in by_name.json()["items"]] == ["PT-0010"]

    by_identifier = client.get(
        "/api/v1/patients", headers=_auth(token), params={"search": "0020"}
    )
    assert [i["identifier"] for i in by_identifier.json()["items"]] == ["PT-0020"]


def test_sort_by_last_name_descending(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin4@cardiacai-test.dev", role="ADMIN")
    make_patient(db_session, demo_org, identifier="PT-A1", last_name="Aaron")
    make_patient(db_session, demo_org, identifier="PT-Z1", last_name="Zimmer")

    token = _login(client, "admin4@cardiacai-test.dev")
    response = client.get(
        "/api/v1/patients", headers=_auth(token), params={"sort_by": "last_name", "sort_dir": "desc"}
    )
    identifiers = [i["identifier"] for i in response.json()["items"]]
    assert identifiers == ["PT-Z1", "PT-A1"]


def test_diagnosis_filter(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin5@cardiacai-test.dev", role="ADMIN")
    make_patient(db_session, demo_org, identifier="PT-D1", registered_diagnosis="DCM")
    make_patient(db_session, demo_org, identifier="PT-D2", registered_diagnosis="HCM")

    token = _login(client, "admin5@cardiacai-test.dev")
    response = client.get(
        "/api/v1/patients", headers=_auth(token), params={"diagnosis": "DCM"}
    )
    assert [i["identifier"] for i in response.json()["items"]] == ["PT-D1"]


def test_study_date_range_filter(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin6@cardiacai-test.dev", role="ADMIN")
    early_patient = make_patient(db_session, demo_org, identifier="PT-E1")
    late_patient = make_patient(db_session, demo_org, identifier="PT-L1")
    make_study(db_session, patient=early_patient, study_date="2020-01-01")
    make_study(db_session, patient=late_patient, study_date="2026-06-01")

    token = _login(client, "admin6@cardiacai-test.dev")
    response = client.get(
        "/api/v1/patients",
        headers=_auth(token),
        params={"study_date_from": "2025-01-01", "study_date_to": "2026-12-31"},
    )
    assert [i["identifier"] for i in response.json()["items"]] == ["PT-L1"]


def test_patient_list_shows_last_study_and_assigned_doctor(client, db_session, demo_org):
    doctor = make_user(db_session, demo_org, email="doc3@cardiacai-test.dev", role="DOCTOR")
    make_user(db_session, demo_org, email="admin7@cardiacai-test.dev", role="ADMIN")
    patient = make_patient(db_session, demo_org, identifier="PT-S1")
    assign_doctor(db_session, patient=patient, doctor=doctor)
    make_study(db_session, patient=patient, study_date="2026-01-01", status="COMPLETED")

    token = _login(client, "admin7@cardiacai-test.dev")
    response = client.get("/api/v1/patients", headers=_auth(token))
    item = response.json()["items"][0]
    assert item["last_study_date"] == "2026-01-01"
    assert item["last_study_status"] == "COMPLETED"
    assert item["assigned_doctor_names"] == ["doc3"]


def test_patient_list_shows_last_analysis_and_low_confidence_filter(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin10@cardiacai-test.dev", role="ADMIN")
    confident_patient = make_patient(db_session, demo_org, identifier="PT-CONF")
    confident_study = make_study(db_session, patient=confident_patient)
    make_ai_analysis(db_session, study=confident_study, predicted_class="NORMAL", confidence=0.95)

    unsure_patient = make_patient(db_session, demo_org, identifier="PT-UNSURE")
    unsure_study = make_study(db_session, patient=unsure_patient)
    make_ai_analysis(db_session, study=unsure_study, predicted_class="MYOCARDIAL_INFARCTION", confidence=0.42)

    token = _login(client, "admin10@cardiacai-test.dev")

    full_list = client.get("/api/v1/patients", headers=_auth(token)).json()
    by_identifier = {item["identifier"]: item for item in full_list["items"]}
    assert by_identifier["PT-CONF"]["last_analysis_predicted_class"] == "NORMAL"
    assert by_identifier["PT-CONF"]["last_analysis_confidence"] == pytest.approx(0.95)
    assert by_identifier["PT-UNSURE"]["last_analysis_confidence"] == pytest.approx(0.42)

    filtered = client.get("/api/v1/patients?low_confidence=true", headers=_auth(token)).json()
    assert [item["identifier"] for item in filtered["items"]] == ["PT-UNSURE"]


def test_assign_doctor_rejects_non_doctor_user(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin8@cardiacai-test.dev", role="ADMIN")
    non_doctor = make_user(db_session, demo_org, email="annot@cardiacai-test.dev", role="ANNOTATOR")
    patient = make_patient(db_session, demo_org, identifier="PT-N1")

    token = _login(client, "admin8@cardiacai-test.dev")
    response = client.post(
        f"/api/v1/patients/{patient.id}/assignments",
        headers=_auth(token),
        json={"patient_id": str(patient.id), "doctor_user_id": str(non_doctor.id)},
    )
    assert response.status_code == 400
