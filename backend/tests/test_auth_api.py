from tests.conftest import make_user


def test_login_success_returns_tokens(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doctor@cardiacai-test.dev", role="DOCTOR", password="Str0ng-Password!")

    response = client.post(
        "/api/v1/auth/login", json={"email": "doctor@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body and "refresh_token" in body


def test_login_wrong_password_rejected(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doctor2@cardiacai-test.dev", role="DOCTOR", password="Str0ng-Password!")

    response = client.post(
        "/api/v1/auth/login", json={"email": "doctor2@cardiacai-test.dev", "password": "wrong"}
    )

    assert response.status_code == 401


def test_login_unknown_email_rejected(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "nobody@cardiacai-test.dev", "password": "whatever"}
    )
    assert response.status_code == 401


def test_account_locks_after_max_failed_attempts(client, db_session, demo_org):
    make_user(db_session, demo_org, email="lockout@cardiacai-test.dev", role="DOCTOR", password="Str0ng-Password!")

    for _ in range(5):
        client.post(
            "/api/v1/auth/login", json={"email": "lockout@cardiacai-test.dev", "password": "wrong"}
        )

    # Even the *correct* password must now be rejected: the account is locked.
    response = client.post(
        "/api/v1/auth/login", json={"email": "lockout@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )
    assert response.status_code == 401


def test_refresh_rotates_token_and_old_one_becomes_invalid(client, db_session, demo_org):
    make_user(db_session, demo_org, email="refresh@cardiacai-test.dev", role="DOCTOR", password="Str0ng-Password!")
    login = client.post(
        "/api/v1/auth/login", json={"email": "refresh@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )
    old_refresh = login.json()["refresh_token"]

    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refreshed.status_code == 200
    new_refresh = refreshed.json()["refresh_token"]
    assert new_refresh != old_refresh

    # Reusing the rotated-away token must fail (theft-detection behavior).
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reused.status_code == 401

    # And the *new* token that came out of a reuse-triggered mass revocation
    # must also no longer work.
    also_revoked = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert also_revoked.status_code == 401


def test_logout_revokes_refresh_token(client, db_session, demo_org):
    make_user(db_session, demo_org, email="logout@cardiacai-test.dev", role="DOCTOR", password="Str0ng-Password!")
    login = client.post(
        "/api/v1/auth/login", json={"email": "logout@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )
    refresh_token = login.json()["refresh_token"]

    logout = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401


def test_me_requires_bearer_token(client):
    response = client.get("/api/v1/users/me")
    assert response.status_code in (401, 403)  # HTTPBearer 403s when no header at all


def test_me_returns_current_user(client, db_session, demo_org):
    make_user(db_session, demo_org, email="me@cardiacai-test.dev", role="DOCTOR", password="Str0ng-Password!")
    login = client.post(
        "/api/v1/auth/login", json={"email": "me@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )
    access_token = login.json()["access_token"]

    response = client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {access_token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@cardiacai-test.dev"
    assert response.json()["roles"] == ["DOCTOR"]
