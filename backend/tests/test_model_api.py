"""Model governance: review (approve/reject, mandatory justification),
promote to production, and rollback — see docs/permissions.md.

The EPIC-4 tests below (MLflow Registry stage sync) mock
app.services.model_service.MlflowClient directly — unlike
test_training_api.py, which exercises the real (sqlite-backed) mlflow
client — because the behaviour under test here is specifically "did we call
the right MlflowClient method with the right arguments", which a mock
verifies more directly than reading back registry state would."""
from app.services import model_service
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


# --- EPIC-4: MLflow Registry stage sync on review()/promote(), and the
# manual registry-divergence reconciliation endpoint. ---


class _FakeMlflowClient:
    """Records every transition_model_version_stage call instead of hitting
    MLflow — used to assert the exact mapping/arguments EPIC-4 specifies."""

    calls: list[dict] = []

    def __init__(self) -> None:
        pass

    def transition_model_version_stage(self, *, name, version, stage, archive_existing_versions):
        self.__class__.calls.append(
            {"name": name, "version": version, "stage": stage, "archive_existing_versions": archive_existing_versions}
        )


class _FailingMlflowClient:
    def transition_model_version_stage(self, **kwargs):
        raise RuntimeError("mlflow registry unreachable")

    def get_model_version(self, name, version):
        raise RuntimeError("mlflow registry unreachable")


def test_review_approve_transitions_mlflow_stage_to_staging(client, db_session, demo_org, monkeypatch):
    make_user(db_session, demo_org, email="approver-reg1@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver-reg1@cardiacai-test.dev")

    monkeypatch.setattr(_FakeMlflowClient, "calls", [])
    monkeypatch.setattr(model_service, "MlflowClient", _FakeMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Meets the accuracy bar"},
    )
    assert response.status_code == 200
    assert _FakeMlflowClient.calls == [
        {
            "name": model_version.mlflow_registry_name, "version": model_version.mlflow_registry_version,
            "stage": "Staging", "archive_existing_versions": False,
        }
    ]


def test_review_reject_transitions_mlflow_stage_to_archived(client, db_session, demo_org, monkeypatch):
    make_user(db_session, demo_org, email="approver-reg2@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver-reg2@cardiacai-test.dev")

    monkeypatch.setattr(_FakeMlflowClient, "calls", [])
    monkeypatch.setattr(model_service, "MlflowClient", _FakeMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": False, "justification": "Accuracy too low"},
    )
    assert response.status_code == 200
    assert _FakeMlflowClient.calls == [
        {
            "name": model_version.mlflow_registry_name, "version": model_version.mlflow_registry_version,
            "stage": "Archived", "archive_existing_versions": False,
        }
    ]


def test_promote_transitions_new_and_demoted_versions_in_mlflow(client, db_session, demo_org, monkeypatch):
    make_user(db_session, demo_org, email="approver-reg3@cardiacai-test.dev", role="MODEL_APPROVER")
    token = _login(client, "approver-reg3@cardiacai-test.dev")

    first = make_model_version(db_session, status="APPROVED")
    client.post(
        f"/api/v1/model-versions/{first.id}/promote", headers=_auth(token), json={"justification": "First release"},
    ).raise_for_status()

    second = make_model_version(db_session, status="APPROVED")
    monkeypatch.setattr(_FakeMlflowClient, "calls", [])
    monkeypatch.setattr(model_service, "MlflowClient", _FakeMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{second.id}/promote", headers=_auth(token), json={"justification": "Better model"},
    )
    assert response.status_code == 200
    assert _FakeMlflowClient.calls == [
        {
            "name": second.mlflow_registry_name, "version": second.mlflow_registry_version,
            "stage": "Production", "archive_existing_versions": False,
        },
        {
            "name": first.mlflow_registry_name, "version": first.mlflow_registry_version,
            "stage": "Archived", "archive_existing_versions": False,
        },
    ]


class _PartiallyFailingMlflowClient:
    """Succeeds on the first transition_model_version_stage call (the
    promoted version -> Production) and fails on every call after that
    (the demoted version -> Archived, and the best-effort revert of the
    first transition) — used to verify promote()'s partial-failure
    handling without leaving MLflow showing two "Production" versions."""

    calls: list[dict] = []

    def transition_model_version_stage(self, *, name, version, stage, archive_existing_versions):
        self.__class__.calls.append(
            {"name": name, "version": version, "stage": stage, "archive_existing_versions": archive_existing_versions}
        )
        if len(self.__class__.calls) > 1:
            raise RuntimeError("mlflow registry unreachable")


def test_promote_reverts_the_first_mlflow_transition_when_the_second_fails(
    client, db_session, demo_org, monkeypatch
):
    """Regression test for EPIC-4's security-review finding: if demoting the
    previous production version in MLflow fails after the new version was
    already transitioned to Production there, promote() must best-effort
    revert that first transition — otherwise MLflow keeps showing the new
    version as Production while the local status rolls back, a divergence
    created by this very call instead of by real drift."""
    make_user(db_session, demo_org, email="approver-reg6@cardiacai-test.dev", role="MODEL_APPROVER")
    token = _login(client, "approver-reg6@cardiacai-test.dev")

    first = make_model_version(db_session, status="APPROVED")
    client.post(
        f"/api/v1/model-versions/{first.id}/promote", headers=_auth(token), json={"justification": "First release"},
    ).raise_for_status()

    second = make_model_version(db_session, status="APPROVED")
    monkeypatch.setattr(_PartiallyFailingMlflowClient, "calls", [])
    monkeypatch.setattr(model_service, "MlflowClient", _PartiallyFailingMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{second.id}/promote", headers=_auth(token), json={"justification": "Better model"},
    )
    assert response.status_code == 502

    unchanged = client.get(f"/api/v1/model-versions/{second.id}", headers=_auth(token))
    assert unchanged.json()["status"] == "APPROVED"
    # 3 calls: promote `second` to Production (succeeds), demote `first` to
    # Archived (fails), then the best-effort revert of `second` back to its
    # previous stage (also fails, but is still attempted).
    assert [c["name"] for c in _PartiallyFailingMlflowClient.calls] == [
        second.mlflow_registry_name, first.mlflow_registry_name, second.mlflow_registry_name,
    ]
    assert [c["stage"] for c in _PartiallyFailingMlflowClient.calls] == ["Production", "Archived", "Staging"]


def test_review_returns_502_and_does_not_persist_status_when_mlflow_fails(client, db_session, demo_org, monkeypatch):
    make_user(db_session, demo_org, email="approver-reg4@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver-reg4@cardiacai-test.dev")

    monkeypatch.setattr(model_service, "MlflowClient", _FailingMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Meets the accuracy bar"},
    )
    assert response.status_code == 502

    unchanged = client.get(f"/api/v1/model-versions/{model_version.id}", headers=_auth(token))
    assert unchanged.json()["status"] == "PENDING_REVIEW"


def test_promote_returns_502_and_does_not_persist_status_when_mlflow_fails(client, db_session, demo_org, monkeypatch):
    make_user(db_session, demo_org, email="approver-reg5@cardiacai-test.dev", role="MODEL_APPROVER")
    token = _login(client, "approver-reg5@cardiacai-test.dev")
    model_version = make_model_version(db_session, status="APPROVED")

    monkeypatch.setattr(model_service, "MlflowClient", _FailingMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/promote",
        headers=_auth(token), json={"justification": "Ship it"},
    )
    assert response.status_code == 502

    unchanged = client.get(f"/api/v1/model-versions/{model_version.id}", headers=_auth(token))
    assert unchanged.json()["status"] == "APPROVED"


def test_registry_divergence_endpoint_reports_an_unreachable_version_without_failing_the_whole_report(
    client, db_session, demo_org, monkeypatch
):
    """Regression test for EPIC-4's security-review finding: a pre-EPIC-4
    row backfilled with the mlflow_registry_version="0" sentinel (migration
    0009) doesn't resolve in MLflow, but that must surface as a per-row
    `fetch_error` entry, not a 502 that hides every other real divergence
    behind one bad reference."""
    make_user(db_session, demo_org, email="approver-div3@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session, status="APPROVED")

    class _UnreachableClient:
        def get_model_version(self, name, version):
            raise RuntimeError("Registered model version not found")

    monkeypatch.setattr(model_service, "MlflowClient", _UnreachableClient)
    token = _login(client, "approver-div3@cardiacai-test.dev")

    response = client.get("/api/v1/model-versions/registry-divergence", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "model_version_id": str(model_version.id), "local_status": "APPROVED",
            "expected_stage": "Staging", "actual_stage": None,
            "fetch_error": "RuntimeError: Registered model version not found",
        }
    ]


def test_registry_divergence_endpoint_detects_a_mismatch(client, db_session, demo_org, monkeypatch):
    make_user(db_session, demo_org, email="approver-div1@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session, status="APPROVED")  # expects Staging in MLflow

    class _MismatchedVersion:
        current_stage = "Production"

    class _MismatchClient:
        def get_model_version(self, name, version):
            return _MismatchedVersion()

    monkeypatch.setattr(model_service, "MlflowClient", _MismatchClient)
    token = _login(client, "approver-div1@cardiacai-test.dev")

    response = client.get("/api/v1/model-versions/registry-divergence", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "model_version_id": str(model_version.id), "local_status": "APPROVED",
            "expected_stage": "Staging", "actual_stage": "Production", "fetch_error": None,
        }
    ]


def test_registry_divergence_endpoint_reports_nothing_for_a_freshly_registered_version(client, db_session, demo_org):
    """No mock here: make_model_version genuinely registers the version in
    the (real, sqlite-backed) MLflow store, at its default stage — which
    matches what a PENDING_REVIEW model version expects (EPIC-4 point 4)."""
    make_user(db_session, demo_org, email="approver-div2@cardiacai-test.dev", role="MODEL_APPROVER")
    make_model_version(db_session)
    token = _login(client, "approver-div2@cardiacai-test.dev")

    response = client.get("/api/v1/model-versions/registry-divergence", headers=_auth(token))
    assert response.status_code == 200
    assert response.json() == []


def test_non_model_approver_view_role_can_read_registry_divergence(client, db_session, demo_org):
    make_user(db_session, demo_org, email="ml-div@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml-div@cardiacai-test.dev")

    response = client.get("/api/v1/model-versions/registry-divergence", headers=_auth(token))
    assert response.status_code == 200


def test_unauthorized_role_cannot_read_registry_divergence(client, db_session, demo_org):
    make_user(db_session, demo_org, email="doc-div@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc-div@cardiacai-test.dev")

    response = client.get("/api/v1/model-versions/registry-divergence", headers=_auth(token))
    assert response.status_code == 403
