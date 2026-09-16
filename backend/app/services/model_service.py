"""Model governance: review a candidate's evaluation, approve/reject it with
a mandatory justification, and promote a validated model to production (or
roll back to a previous one) — see docs/permissions.md, which is explicit
that ADMIN cannot do any of this "merely by being an administrator"; it's
MODEL_APPROVER-only, and every decision here is justified, not just logged.

Per ADR-2/EPIC-4: MLflow Model Registry is the source of truth for the
artifact's technical stage, this module's ModelVersion.status stays the
source of truth for the human-approval workflow. Every status change here
also transitions the matching MLflow Registry stage, in the same
(unflushed-to-commit) unit of work — see _STAGE_BY_STATUS and
_transition_stage.
"""
from dataclasses import dataclass

from mlflow.tracking import MlflowClient
from sqlalchemy.orm import Session

from app.core.enums import ApprovalDecision, ModelVersionStatus
from app.models.model_approval import ModelApproval
from app.models.model_version import ModelVersion
from app.models.user import User
from app.repositories import audit_repository, model_repository

# ModelVersionStatus -> MLflow Registry stage (EPIC-4, "Contrato técnico",
# point 2). None means "leave whatever register_model assigned by default,
# no transition needed" (PENDING_REVIEW).
_STAGE_BY_STATUS: dict[str, str | None] = {
    ModelVersionStatus.PENDING_REVIEW.value: None,
    ModelVersionStatus.APPROVED.value: "Staging",
    ModelVersionStatus.REJECTED.value: "Archived",
    ModelVersionStatus.PRODUCTION.value: "Production",
    ModelVersionStatus.RETIRED.value: "Archived",
}


class MissingJustificationError(ValueError):
    pass


class InvalidModelStateError(ValueError):
    pass


class ModelRegistrySyncError(RuntimeError):
    """Raised when transitioning a ModelVersion's MLflow Registry stage
    fails (connectivity or any other mlflow/MlflowClient error). Left to
    propagate uncaught by review()/promote() — since only db.flush() (never
    db.commit()) has happened by that point, the local status change is
    discarded automatically when the session closes without a manual
    rollback (see app.db.session.get_db and EPIC-4 point 6)."""


def _require_justification(justification: str) -> None:
    if not justification or not justification.strip():
        raise MissingJustificationError("a justification is required for this decision")


def _transition_stage(model_version: ModelVersion, stage: str) -> None:
    try:
        MlflowClient().transition_model_version_stage(
            name=model_version.mlflow_registry_name,
            version=model_version.mlflow_registry_version,
            stage=stage,
            archive_existing_versions=False,
            # archive_existing_versions is explicitly False: demoting a
            # previous production version to Archived is handled by
            # promote() itself, not MLflow's automatic mechanism.
        )
    except Exception as exc:  # noqa: BLE001 — any mlflow/connectivity failure
        # here is a failure of the whole operation, same criterion
        # training_service.py already applies to mlflow calls.
        raise ModelRegistrySyncError(
            f"failed to sync MLflow registry stage for model version {model_version.id}: {exc}"
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
    model_version.status = (
        ModelVersionStatus.APPROVED.value if approve else ModelVersionStatus.REJECTED.value
    )
    db.flush()
    stage = _STAGE_BY_STATUS[model_version.status]
    if stage is not None:
        _transition_stage(model_version, stage)
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
    at a time (see app.repositories.model_repository.get_production)."""
    _require_justification(justification)
    if model_version.status not in (ModelVersionStatus.APPROVED.value, ModelVersionStatus.RETIRED.value):
        raise InvalidModelStateError("only an APPROVED or RETIRED model version can be promoted")

    previous_status = model_version.status
    current_production = model_repository.get_production(db, model_version.name)
    if current_production is not None and current_production.id != model_version.id:
        current_production.status = ModelVersionStatus.RETIRED.value

    model_version.status = ModelVersionStatus.PRODUCTION.value
    db.flush()
    _transition_stage(model_version, _STAGE_BY_STATUS[ModelVersionStatus.PRODUCTION.value])
    if current_production is not None and current_production.id != model_version.id:
        try:
            _transition_stage(current_production, _STAGE_BY_STATUS[ModelVersionStatus.RETIRED.value])
        except ModelRegistrySyncError:
            # The local status change is about to be discarded (see
            # ModelRegistrySyncError's docstring), so best-effort revert the
            # transition already applied above too — otherwise MLflow would
            # be left showing this version as Production while the local
            # status rolls back to previous_status, which is exactly the
            # kind of divergence check_registry_divergence exists to catch,
            # created needlessly by this very call instead of by drift.
            try:
                _transition_stage(model_version, _STAGE_BY_STATUS[previous_status])
            except ModelRegistrySyncError:
                pass  # best-effort only — the original error is what propagates
            raise
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
    """One ModelVersion whose MLflow Registry stage doesn't match what its
    local `status` implies (EPIC-4 point 4). Reporting only — the local
    `status` stays the source of truth of record (ADR-2); resyncing MLflow
    itself is a deliberate human action, out of scope for this Epic (see
    docs/BACKLOG.md)."""

    model_version_id: str
    local_status: str
    expected_stage: str | None
    actual_stage: str | None
    fetch_error: str | None = None


def check_registry_divergence(db: Session) -> list[RegistryDivergence]:
    """Manual, read-only reconciliation (EPIC-4 point 4): compares, for
    every non-deleted ModelVersion, the MLflow Registry stage it's actually
    in against the stage its local `status` implies it should be in
    (_STAGE_BY_STATUS). Never corrects anything — see RegistryDivergence.

    A PENDING_REVIEW model version has no expected stage (MLflow leaves it
    at whatever register_model assigned by default, usually None) — such a
    version is only reported if MLflow shows it in a stage other than that
    default, which would itself be surprising since nothing in this
    codebase transitions a version before it leaves PENDING_REVIEW.

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
        expected_stage = _STAGE_BY_STATUS[model_version.status]
        try:
            registry_version = client.get_model_version(
                model_version.mlflow_registry_name, model_version.mlflow_registry_version
            )
        except Exception as exc:  # noqa: BLE001 — connectivity/missing-version failures
            divergences.append(
                RegistryDivergence(
                    model_version_id=str(model_version.id), local_status=model_version.status,
                    expected_stage=expected_stage, actual_stage=None,
                    fetch_error=f"{type(exc).__name__}: {exc}",
                )
            )
            continue
        actual_stage = registry_version.current_stage
        # MLflow reports the "no stage" case as the literal string "None",
        # not Python None — normalize before comparing against our mapping.
        if actual_stage == "None":
            actual_stage = None
        if actual_stage != expected_stage:
            divergences.append(
                RegistryDivergence(
                    model_version_id=str(model_version.id), local_status=model_version.status,
                    expected_stage=expected_stage, actual_stage=actual_stage,
                )
            )
    return divergences
