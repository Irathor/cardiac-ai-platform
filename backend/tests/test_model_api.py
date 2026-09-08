"""Model governance: review (approve/reject, mandatory justification),
promote to production, and rollback — see docs/permissions.md."""
from tests.conftest import make_model_version, make_user


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_approver_approves_a_pending_model_version(client, db_session, demo_org):
    make_user(db_session, demo_org, email="approver1@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver1@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Meets the accuracy bar"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"


def test_approver_rejects_a_pending_model_version(client, db_session, demo_org):
    make_user(db_session, demo_org, email="approver2@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver2@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": False, "justification": "Accuracy too low on TEST"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"


def test_review_requires_a_non_empty_justification(client, db_session, demo_org):
    make_user(db_session, demo_org, email="approver3@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver3@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "   "},
    )
    assert response.status_code == 422


def test_cannot_review_an_already_reviewed_model_version(client, db_session, demo_org):
    make_user(db_session, demo_org, email="approver4@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session, status="APPROVED")
    token = _login(client, "approver4@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Again?"},
    )
    assert response.status_code == 409


def test_promote_requires_approval_first(client, db_session, demo_org):
    make_user(db_session, demo_org, email="approver5@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session, status="PENDING_REVIEW")
    token = _login(client, "approver5@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/promote",
        headers=_auth(token), json={"justification": "Ship it"},
    )
    assert response.status_code == 409


def test_promote_demotes_the_previous_production_version_and_rollback_works(client, db_session, demo_org):
    make_user(db_session, demo_org, email="approver6@cardiacai-test.dev", role="MODEL_APPROVER")
    token = _login(client, "approver6@cardiacai-test.dev")

    first = make_model_version(db_session, status="APPROVED")
    promote_first = client.post(
        f"/api/v1/model-versions/{first.id}/promote", headers=_auth(token), json={"justification": "First release"},
    )
    assert promote_first.status_code == 200
    assert promote_first.json()["status"] == "PRODUCTION"

    second = make_model_version(db_session, status="APPROVED")
    promote_second = client.post(
        f"/api/v1/model-versions/{second.id}/promote", headers=_auth(token), json={"justification": "Better model"},
    )
    assert promote_second.status_code == 200
    assert promote_second.json()["status"] == "PRODUCTION"

    first_now = client.get(f"/api/v1/model-versions/{first.id}", headers=_auth(token))
    assert first_now.json()["status"] == "RETIRED"

    # Rollback: promoting the RETIRED first version again re-demotes the second.
    rollback = client.post(
        f"/api/v1/model-versions/{first.id}/promote", headers=_auth(token), json={"justification": "Regression found, rolling back"},
    )
    assert rollback.status_code == 200
    assert rollback.json()["status"] == "PRODUCTION"

    second_now = client.get(f"/api/v1/model-versions/{second.id}", headers=_auth(token))
    assert second_now.json()["status"] == "RETIRED"


def test_non_model_approver_cannot_review_or_promote(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml-approve@cardiacai-test.dev", role="ML_ENGINEER")
    model_version = make_model_version(db_session)
    token = _login(client, "ml-approve@cardiacai-test.dev")

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Not allowed anyway"},
    )
    assert response.status_code == 403
