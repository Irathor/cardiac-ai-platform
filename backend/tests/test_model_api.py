"""Model governance: review (approve/reject, mandatory justification),
promote to production, and rollback — see docs/permissions.md.

The EPIC-4/EPIC-11 tests below (MLflow Registry alias sync, ADR-4) mock
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


# --- EPIC-4/EPIC-11 (ADR-4): MLflow Registry alias sync on promote()
# only — review() no longer talks to MLflow — and the manual
# registry-divergence reconciliation endpoint. ---


class _FakeMlflowClient:
    """Records every set_registered_model_alias/delete_registered_model_alias
    call instead of hitting MLflow — used to assert the exact
    mapping/arguments ADR-4 specifies."""

    calls: list[dict] = []

    def __init__(self) -> None:
        pass

    def set_registered_model_alias(self, *, name, alias, version):
        self.__class__.calls.append({"method": "set_alias", "name": name, "alias": alias, "version": version})

    def delete_registered_model_alias(self, *, name, alias):
        self.__class__.calls.append({"method": "delete_alias", "name": name, "alias": alias})


class _FailingMlflowClient:
    def set_registered_model_alias(self, **kwargs):
        raise RuntimeError("mlflow registry unreachable")

    def delete_registered_model_alias(self, **kwargs):
        raise RuntimeError("mlflow registry unreachable")

    def get_model_version(self, name, version):
        raise RuntimeError("mlflow registry unreachable")


def test_review_never_calls_mlflow(client, db_session, demo_org, monkeypatch):
    """ADR-4: with the alias mapping, PENDING_REVIEW -> APPROVED/REJECTED is
    always None -> None, so review() no longer syncs anything with MLflow
    (unlike the old stage mapping, where approve/reject transitioned to
    Staging/Archived). Covers both branches against the same fake client."""
    make_user(db_session, demo_org, email="approver-reg1@cardiacai-test.dev", role="MODEL_APPROVER")
    approved_version = make_model_version(db_session)
    rejected_version = make_model_version(db_session)
    token = _login(client, "approver-reg1@cardiacai-test.dev")

    monkeypatch.setattr(_FakeMlflowClient, "calls", [])
    monkeypatch.setattr(model_service, "MlflowClient", _FakeMlflowClient)

    approve_response = client.post(
        f"/api/v1/model-versions/{approved_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Meets the accuracy bar"},
    )
    reject_response = client.post(
        f"/api/v1/model-versions/{rejected_version.id}/review",
        headers=_auth(token), json={"approve": False, "justification": "Accuracy too low"},
    )
    assert approve_response.status_code == 200
    assert reject_response.status_code == 200
    assert _FakeMlflowClient.calls == []


def test_review_succeeds_even_if_mlflow_is_unreachable(client, db_session, demo_org, monkeypatch):
    """Direct consequence of ADR-4's decoupling: since review() never talks
    to MLflow, an unreachable MLflow no longer blocks an approval/rejection
    the way it did under the old stage mapping (see the now-removed
    test_review_returns_502_and_does_not_persist_status_when_mlflow_fails)."""
    make_user(db_session, demo_org, email="approver-reg1b@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session)
    token = _login(client, "approver-reg1b@cardiacai-test.dev")

    monkeypatch.setattr(model_service, "MlflowClient", _FailingMlflowClient)

    response = client.post(
        f"/api/v1/model-versions/{model_version.id}/review",
        headers=_auth(token), json={"approve": True, "justification": "Meets the accuracy bar"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "APPROVED"


def test_promote_syncs_production_alias_for_new_and_demoted_versions_in_mlflow(
    client, db_session, demo_org, monkeypatch
):
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
    # `first` loses the "production" alias before `second` gains it — this
    # order isn't arbitrary: delete_registered_model_alias isn't scoped by
    # version, so deleting after the reassignment would strip the alias
    # from `second` (the version it was *just* moved to) instead of doing
    # nothing useful to `first` — see promote()'s docstring.
    assert _FakeMlflowClient.calls == [
        {"method": "delete_alias", "name": first.mlflow_registry_name, "alias": "production"},
        {"method": "set_alias", "name": second.mlflow_registry_name, "alias": "production", "version": second.mlflow_registry_version},
    ]


class _PartiallyFailingMlflowClient:
    """Succeeds on the first alias-sync call (demoting the previous
    production version) and fails on every call after that (assigning
    "production" to the newly promoted version, and the best-effort revert
    of the first call) — used to verify promote()'s partial-failure
    handling without leaving MLflow with no version aliased "production" at
    all while the local status rolls back."""

    calls: list[dict] = []

    def set_registered_model_alias(self, *, name, alias, version):
        self.__class__.calls.append({"method": "set_alias", "name": name, "alias": alias, "version": version})
        raise RuntimeError("mlflow registry unreachable")

    def delete_registered_model_alias(self, *, name, alias):
        self.__class__.calls.append({"method": "delete_alias", "name": name, "alias": alias})


def test_promote_reverts_the_first_mlflow_alias_sync_when_the_second_fails(
    client, db_session, demo_org, monkeypatch
):
    """Regression test for EPIC-4's security-review finding, adapted to the
    alias mechanism (EPIC-11/ADR-4): if assigning "production" to the newly
    promoted version fails in MLflow after the previous production version
    was already demoted (alias deleted) there, promote() must best-effort
    revert that first sync — otherwise MLflow ends up with no version
    aliased "production" for this model name while the local status rolls
    back to the previous version still being PRODUCTION, a divergence
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
    # 3 calls: delete "production" from `first` (succeeds), set "production"
    # on `second` (fails), then the best-effort revert — re-setting
    # "production" back on `first` (also fails, but is still attempted).
    assert [c["method"] for c in _PartiallyFailingMlflowClient.calls] == ["delete_alias", "set_alias", "set_alias"]
    assert [c["name"] for c in _PartiallyFailingMlflowClient.calls] == [
        first.mlflow_registry_name, second.mlflow_registry_name, first.mlflow_registry_name,
    ]


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
    model_version = make_model_version(db_session, status="APPROVED")  # expects no alias (ADR-4)

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
            "expected_alias": None, "actual_alias": None,
            "fetch_error": "RuntimeError: Registered model version not found",
        }
    ]


def test_registry_divergence_endpoint_detects_a_mismatch(client, db_session, demo_org, monkeypatch):
    """APPROVED expects no alias (ADR-4); a version showing "production"
    anyway is contamination, not a legitimate alias for that status."""
    make_user(db_session, demo_org, email="approver-div1@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session, status="APPROVED")

    class _MismatchedVersion:
        aliases = ["production"]

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
            "expected_alias": None, "actual_alias": "production", "fetch_error": None,
        }
    ]


def test_registry_divergence_endpoint_detects_a_missing_production_alias(client, db_session, demo_org, monkeypatch):
    """The inverse of the mismatch case above: PRODUCTION expects
    "production" (ADR-4's only real alias); a version missing it is a
    divergence too, not just an unexpected extra alias."""
    make_user(db_session, demo_org, email="approver-div4@cardiacai-test.dev", role="MODEL_APPROVER")
    model_version = make_model_version(db_session, status="PRODUCTION")

    class _NoAliasVersion:
        aliases = []

    class _NoAliasClient:
        def get_model_version(self, name, version):
            return _NoAliasVersion()

    monkeypatch.setattr(model_service, "MlflowClient", _NoAliasClient)
    token = _login(client, "approver-div4@cardiacai-test.dev")

    response = client.get("/api/v1/model-versions/registry-divergence", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body == [
        {
            "model_version_id": str(model_version.id), "local_status": "PRODUCTION",
            "expected_alias": "production", "actual_alias": None, "fetch_error": None,
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
