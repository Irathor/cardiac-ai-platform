from app.repositories import audit_repository
from tests.conftest import make_user


def test_failed_and_successful_login_are_both_audited(client, db_session, demo_org):
    make_user(db_session, demo_org, email="audited@cardiacai-test.dev", role="DOCTOR")

    client.post("/api/v1/auth/login", json={"email": "audited@cardiacai-test.dev", "password": "wrong"})
    client.post(
        "/api/v1/auth/login", json={"email": "audited@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )

    events = audit_repository.list_recent(db_session)
    login_events = [e for e in events if e.action == "login"]
    assert any(e.result == "failure" for e in login_events)
    assert any(e.result == "success" for e in login_events)


def test_logout_is_audited(client, db_session, demo_org):
    make_user(db_session, demo_org, email="audited2@cardiacai-test.dev", role="DOCTOR")
    login = client.post(
        "/api/v1/auth/login", json={"email": "audited2@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )
    refresh_token = login.json()["refresh_token"]

    client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    events = audit_repository.list_recent(db_session)
    assert any(e.action == "logout" and e.result == "success" for e in events)
