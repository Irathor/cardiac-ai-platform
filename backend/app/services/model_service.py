"""Model governance: review a candidate's evaluation, approve/reject it with
a mandatory justification, and promote a validated model to production (or
roll back to a previous one) — see docs/permissions.md, which is explicit
that ADMIN cannot do any of this "merely by being an administrator"; it's
MODEL_APPROVER-only, and every decision here is justified, not just logged.

Per ADR-2/EPIC-4/ADR-4/EPIC-11: MLflow Model Registry is the source of
truth for the artifact's production status, this module's
ModelVersion.status stays the source of truth for the human-approval
workflow. Only PRODUCTION has a real MLflow alias (`production`) — see
ADR-4 for why the other four statuses deliberately have none: an MLflow
alias is a unique pointer per name (unlike the deprecated stage API, it
can't represent "N versions share this state" the way the local `status`
column allows for APPROVED/REJECTED/RETIRED). Every status change here
syncs the matching MLflow Registry alias, in the same
(unflushed-to-commit) unit of work — see _ALIAS_BY_STATUS and
_sync_alias. Consequence: review() never talks to MLflow anymore (both
its PENDING_REVIEW -> APPROVED and -> REJECTED transitions map to
None -> None); only promote() still can.
"""
from dataclasses import dataclass

from mlflow.tracking import MlflowClient
from sqlalchemy.orm import Session

from app.core.enums import ApprovalDecision, ModelVersionStatus
from app.models.model_approval import ModelApproval
from app.models.model_version import ModelVersion
from app.models.user import User
from app.repositories import audit_repository, model_repository

# ModelVersionStatus -> MLflow Registry alias (ADR-4 / EPIC-11, "Contrato
# técnico", point 2). None means "no alias assigned" — true for every
# status except PRODUCTION, the only one with a local uniqueness invariant
# (model_repository.get_production) that a single-pointer MLflow alias can
# represent without lying about which version is "the" one in that state.
_ALIAS_BY_STATUS: dict[str, str | None] = {
    ModelVersionStatus.PENDING_REVIEW.value: None,
    ModelVersionStatus.APPROVED.value: None,
    ModelVersionStatus.REJECTED.value: None,
    ModelVersionStatus.PRODUCTION.value: "production",
    ModelVersionStatus.RETIRED.value: None,
}


class MissingJustificationError(ValueError):
    pass


class InvalidModelStateError(ValueError):
    pass


class ModelRegistrySyncError(RuntimeError):
    """Raised when syncing a ModelVersion's MLflow Registry alias fails
    (connectivity or any other mlflow/MlflowClient error). Left to
    propagate uncaught by review()/promote() — since only db.flush() (never
    db.commit()) has happened by that point, the local status change is
    discarded automatically when the session closes without a manual
    rollback (see app.db.session.get_db and EPIC-4 point 6). In practice
    only promote() can raise this today: review()'s status transitions
    (PENDING_REVIEW -> APPROVED/REJECTED) map to None -> None in
    _ALIAS_BY_STATUS, so _sync_alias never calls MLflow for them (ADR-4)."""


def _require_justification(justification: str) -> None:
    if not justification or not justification.strip():
        raise MissingJustificationError("a justification is required for this decision")


def _sync_alias(model_version: ModelVersion, previous_status: str, new_status: str) -> None:
    """Syncs `model_version`'s MLflow Registry alias to match `new_status`,
    per _ALIAS_BY_STATUS (ADR-4 / EPIC-11, "Contrato técnico", point 1).

    An MLflow alias is a unique pointer per name — reassigning it to a new
    version automatically retires it from whichever version held it before,
    with no explicit delete call needed for that case (verified against the
    real API, mlflow 3.16.1: FileStore.set_registered_model_alias
    overwrites rather than accumulates). So the only explicit delete this
    function issues is for *this* version losing an alias that isn't being
    replaced by the same name in the same call — e.g. the outgoing side of
    a PRODUCTION -> RETIRED demotion, where old_alias="production" and
    new_alias=None.
    """
    old_alias = _ALIAS_BY_STATUS[previous_status]
    new_alias = _ALIAS_BY_STATUS[new_status]
    if old_alias == new_alias:
        return  # no-op, includes the common None -> None case
    try:
        if old_alias is not None:
            MlflowClient().delete_registered_model_alias(
                name=model_version.mlflow_registry_name, alias=old_alias,
            )
        if new_alias is not None:
            MlflowClient().set_registered_model_alias(
                name=model_version.mlflow_registry_name, alias=new_alias,
                version=model_version.mlflow_registry_version,
            )
    except Exception as exc:  # noqa: BLE001 — any mlflow/connectivity failure
        # here is a failure of the whole operation, same criterion
        # training_service.py already applies to mlflow calls.
        raise ModelRegistrySyncError(
            f"failed to sync MLflow registry alias for model version {model_version.id}: {exc}"
        ) from exc


def review(
    db: Session, *, approver: User, model_version: ModelVersion, approve: bool, justification: str
) -> ModelApproval:
    _require_justification(justification)
    if model_version.status != ModelVersionStatus.PENDING_REVIEW.value:
        raise InvalidModelStateError("only a PENDING_REVIEW model version can be reviewed")

    decision = ApprovalDecision.APPROVED.value if approve else ApprovalDecision.REJECTED.value
    approval = model_repository.create_approval(
        db, model_version_id=model_version.id, approver_id=approver.id,
        decision=decision, justification=justification,
    )
    new_status = ModelVersionStatus.APPROVED.value if approve else ModelVersionStatus.REJECTED.value
    old_status = model_version.status
    model_version.status = new_status
    db.flush()
    # PENDING_REVIEW -> APPROVED/REJECTED is always None -> None in
    # _ALIAS_BY_STATUS (ADR-4): this call never actually reaches MLflow
    # today, kept for consistency/future-proofing (see this module's
    # docstring and _sync_alias).
    _sync_alias(model_version, old_status, new_status)
    audit_repository.record(
        db, user_id=approver.id, action="model_version_reviewed", resource_type="model_version",
        resource_id=str(model_version.id), result="success",
        event_metadata={"decision": decision, "justification": justification},
    )
    return approval


def promote(db: Session, *, approver: User, model_version: ModelVersion, justification: str) -> ModelVersion:
    """Promotes an APPROVED or RETIRED (rollback) model version to
    PRODUCTION, demoting whatever else currently holds that name's
    production slot to RETIRED. Only one PRODUCTION version per model name
    at a time (see app.repositories.model_repository.get_production).

    Per ADR-4, `production` is the only status with a real MLflow alias, so
    this is the only operation in this module that still talks to MLflow
    (review() no longer does).

    Call order matters here in a way it never did with the deprecated stage
    API: `MlflowClient.delete_registered_model_alias(name, alias)` isn't
    scoped to a version — it deletes whichever version currently holds that
    alias name, full stop (verified against the real API, mlflow 3.16.1).
    So the demoted version's alias MUST be dropped *before* the new
    version's alias is set, not after: if the order were reversed (set
    first, delete second), the delete call would strip the alias that was
    *just* reassigned to the newly promoted version, not the one still
    sitting on the demoted version — leaving neither version aliased
    `production`. This was caught by this Epic's real-MLflow-server
    end-to-end check (see EPIC-11), not by the existing test suite: every
    prior test only asserted the local `status` column, which stayed
    correct regardless of this MLflow-side bug — a reminder that a DB-only
    assertion can't catch a divergence that lives entirely in MLflow."""
    _require_justification(justification)
    if model_version.status not in (ModelVersionStatus.APPROVED.value, ModelVersionStatus.RETIRED.value):
        raise InvalidModelStateError("only an APPROVED or RETIRED model version can be promoted")

    previous_status = model_version.status
    current_production = model_repository.get_production(db, model_version.name)
    if current_production is not None and current_production.id != model_version.id:
        current_production.status = ModelVersionStatus.RETIRED.value

    model_version.status = ModelVersionStatus.PRODUCTION.value
    db.flush()
    if current_production is not None and current_production.id != model_version.id:
        # Demote first (releases the "production" alias name) so the
        # promote call below can claim it without racing its own delete —
        # see this function's docstring.
        _sync_alias(current_production, ModelVersionStatus.PRODUCTION.value, ModelVersionStatus.RETIRED.value)
        try:
            _sync_alias(model_version, previous_status, ModelVersionStatus.PRODUCTION.value)
        except ModelRegistrySyncError:
            # The local status change is about to be discarded (see
            # ModelRegistrySyncError's docstring), so best-effort revert the
            # demotion already applied above too — otherwise MLflow would be
            # left with no version aliased "production" for this model name
            # while the local status rolls back to current_production still
            # being PRODUCTION, which is exactly the kind of divergence
            # check_registry_divergence exists to catch, created needlessly
            # by this very call instead of by drift.
            try:
                _sync_alias(current_production, ModelVersionStatus.RETIRED.value, ModelVersionStatus.PRODUCTION.value)
            except ModelRegistrySyncError:
                pass  # best-effort only — the original error is what propagates
            raise
    else:
        _sync_alias(model_version, previous_status, ModelVersionStatus.PRODUCTION.value)
    audit_repository.record(
        db, user_id=approver.id, action="model_version_promoted", resource_type="model_version",
        resource_id=str(model_version.id), result="success",
        event_metadata={
            "justification": justification,
            "demoted_model_version_id": str(current_production.id) if current_production else None,
        },
    )
    return model_version


@dataclass
class RegistryDivergence:
    """One ModelVersion whose MLflow Registry alias doesn't match what its
    local `status` implies (EPIC-4 point 4 / ADR-4 / EPIC-11 point 3).
    Reporting only — the local `status` stays the source of truth of record
    (ADR-2); resyncing MLflow itself is a deliberate human action, out of
    scope for this Epic (see docs/BACKLOG.md).

    `expected_alias`/`actual_alias` (renamed from `expected_stage`/
    `actual_stage` in EPIC-11 — MLflow's alias API replaces the deprecated
    stage API) hold a single alias name for the common case, or a
    comma-joined list if `actual_alias` ever shows more than one alias on
    the same version (a form of divergence itself: today's mapping never
    assigns more than one alias per version, so more than one present is
    already contamination, e.g. leftover from a manual/legacy operation)."""

    model_version_id: str
    local_status: str
    expected_alias: str | None
    actual_alias: str | None
    fetch_error: str | None = None


def check_registry_divergence(db: Session) -> list[RegistryDivergence]:
    """Manual, read-only reconciliation (EPIC-4 point 4 / ADR-4 / EPIC-11
    point 3): compares, for every non-deleted ModelVersion, the MLflow
    Registry alias(es) it actually has against the alias its local `status`
    implies it should have (_ALIAS_BY_STATUS). Never corrects anything —
    see RegistryDivergence.

    A ModelVersion whose status maps to no alias (every status except
    PRODUCTION, per ADR-4) expects an empty alias set — it's only reported
    if MLflow shows it carrying an alias anyway, which would itself be
    surprising since nothing in this codebase assigns one for those
    statuses.

    A model version MLflow can't be reached for (connectivity, or a
    registry reference that doesn't resolve — e.g. a pre-EPIC-4 row
    backfilled with the `mlflow_registry_version="0"` sentinel by migration
    0009, since MLflow versions start at 1) is reported as a divergence
    entry with `fetch_error` set, not raised — one unreachable/invalid
    reference must not hide every other real divergence behind a 502 for
    the whole reconciliation run.
    """
    client = MlflowClient()
    divergences: list[RegistryDivergence] = []
    for model_version in model_repository.list_all(db):
        expected_alias = _ALIAS_BY_STATUS[model_version.status]
        expected_aliases = {expected_alias} if expected_alias is not None else set()
        try:
            registry_version = client.get_model_version(
                model_version.mlflow_registry_name, model_version.mlflow_registry_version
            )
        except Exception as exc:  # noqa: BLE001 — connectivity/missing-version failures
            divergences.append(
                RegistryDivergence(
                    model_version_id=str(model_version.id), local_status=model_version.status,
                    expected_alias=expected_alias, actual_alias=None,
                    fetch_error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        actual_aliases = set(registry_version.aliases or [])
        if actual_aliases != expected_aliases:
            divergences.append(
                RegistryDivergence(
                    model_version_id=str(model_version.id), local_status=model_version.status,
                    expected_alias=expected_alias,
                    actual_alias=", ".join(sorted(actual_aliases)) if actual_aliases else None,
                )
            )
    return divergences
