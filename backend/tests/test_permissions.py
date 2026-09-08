"""Authorization must be enforced by the API itself, never assumed from the
UI — these tests call the endpoints directly, the same way a manipulated
HTTP request would (see docs/permissions.md)."""
from tests.conftest import make_user


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_doctor_cannot_list_users(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doc@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc@cardiacai-test.dev")

    response = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_doctor_cannot_create_users(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doc2@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc2@cardiacai-test.dev")

    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "new@cardiacai-test.dev", "full_name": "New Person", "password": "x", "roles": []},
    )
    assert response.status_code == 403


def test_admin_can_list_and_create_users(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin@cardiacai-test.dev", role="ADMIN")
    token = _login(client, "admin@cardiacai-test.dev")

    listing = client.get("/api/v1/users", headers={"Authorization": f"Bearer {token}"})
    assert listing.status_code == 200
    assert any(u["email"] == "admin@cardiacai-test.dev" for u in listing.json())

    created = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "newdoctor@cardiacai-test.dev",
            "full_name": "New Doctor",
            "password": "Str0ng-Password!",
            "roles": ["DOCTOR"],
        },
    )
    assert created.status_code == 201
    assert created.json()["roles"] == ["DOCTOR"]


def test_admin_cannot_assign_unknown_role(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin2@cardiacai-test.dev", role="ADMIN")
    token = _login(client, "admin2@cardiacai-test.dev")

    response = client.post(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "email": "bad@cardiacai-test.dev",
            "full_name": "Bad Role",
            "password": "Str0ng-Password!",
            "roles": ["SUPERUSER"],
        },
    )
    assert response.status_code == 400


def test_admin_can_deactivate_user_and_deactivated_user_cannot_login(client, db_session, demo_org):
    make_user(db_session, demo_org, email="admin3@cardiacai-test.dev", role="ADMIN")
    target = make_user(db_session, demo_org, email="target@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "admin3@cardiacai-test.dev")

    response = client.patch(
        f"/api/v1/users/{target.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"is_active": False},
    )
    assert response.status_code == 200
    assert response.json()["is_active"] is False

    login = client.post(
        "/api/v1/auth/login", json={"email": "target@cardiacai-test.dev", "password": "Str0ng-Password!"}
    )
    assert login.status_code == 401
