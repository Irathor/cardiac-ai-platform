"""Model governance: review a candidate's evaluation, approve/reject it with
a mandatory justification, and promote a validated model to production (or
roll back to a previous one) — see docs/permissions.md, which is explicit
that ADMIN cannot do any of this "merely by being an administrator"; it's
MODEL_APPROVER-only, and every decision here is justified, not just logged.
"""
from sqlalchemy.orm import Session

from app.core.enums import ApprovalDecision, ModelVersionStatus
from app.models.model_approval import ModelApproval
from app.models.model_version import ModelVersion
from app.models.user import User
from app.repositories import audit_repository, model_repository


class MissingJustificationError(ValueError):
    pass


class InvalidModelStateError(ValueError):
    pass


def _require_justification(justification: str) -> None:
    if not justification or not justification.strip():
        raise MissingJustificationError("a justification is required for this decision")


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

    current_production = model_repository.get_production(db, model_version.name)
    if current_production is not None and current_production.id != model_version.id:
        current_production.status = ModelVersionStatus.RETIRED.value

    model_version.status = ModelVersionStatus.PRODUCTION.value
    db.flush()
    audit_repository.record(
        db, user_id=approver.id, action="model_version_promoted", resource_type="model_version",
        resource_id=str(model_version.id), result="success",
        event_metadata={
            "justification": justification,
            "demoted_model_version_id": str(current_production.id) if current_production else None,
        },
    )
    return model_version
