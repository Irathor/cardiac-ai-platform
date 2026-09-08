"""Dataset versioning: only APPROVED annotations (ground truth) can become a
DatasetCase, splits are enforced at the patient level (a patient's cases can
never span TRAIN/VALIDATION/TEST within one version — that would leak
information between splits), and a LOCKED version is immutable, stamped with
a checksum over its exact case membership (see docs/phases.md).
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.enums import AnnotationStatus, DatasetVersionStatus
from app.models.annotation import Annotation
from app.models.dataset import Dataset
from app.models.dataset_case import DatasetCase
from app.models.dataset_version import DatasetVersion
from app.models.user import User
from app.repositories import annotation_repository, audit_repository, dataset_repository


class AnnotationNotApprovedError(ValueError):
    pass


class AnnotationHasNoPatientError(ValueError):
    """Should be unreachable in practice — an Annotation always traces back
    to a patient through its segmentation/series/study — but the underlying
    study or series is a nullable FK chain, so this is checked rather than
    assumed."""


class PatientSplitConflictError(ValueError):
    pass


class DatasetVersionLockedError(ValueError):
    pass


class EmptyDatasetVersionError(ValueError):
    pass


def create_dataset(db: Session, *, actor: User, name: str, description: str | None = None) -> Dataset:
    dataset = dataset_repository.create(db, created_by=actor.id, name=name, description=description)
    audit_repository.record(
        db, user_id=actor.id, action="dataset_created", resource_type="dataset",
        resource_id=str(dataset.id), result="success",
    )
    return dataset


def create_version(db: Session, *, actor: User, dataset: Dataset) -> DatasetVersion:
    version_number = dataset_repository.next_version_number(db, dataset.id)
    version = dataset_repository.create_version(
        db, dataset_id=dataset.id, created_by=actor.id,
        version_number=version_number, status=DatasetVersionStatus.DRAFT.value,
    )
    audit_repository.record(
        db, user_id=actor.id, action="dataset_version_created", resource_type="dataset_version",
        resource_id=str(version.id), result="success",
        event_metadata={"dataset_id": str(dataset.id), "version_number": version_number},
    )
    return version


def add_case(
    db: Session, *, actor: User, version: DatasetVersion, annotation: Annotation, split: str
) -> DatasetCase:
    if version.status == DatasetVersionStatus.LOCKED.value:
        raise DatasetVersionLockedError("cannot add cases to a LOCKED dataset version")
    if annotation.status != AnnotationStatus.APPROVED.value:
        raise AnnotationNotApprovedError("only an APPROVED annotation can be selected into a dataset")

    patient_id = annotation_repository.get_patient_id(db, annotation)
    if patient_id is None:
        raise AnnotationHasNoPatientError()

    existing = dataset_repository.get_case_for_patient(
        db, dataset_version_id=version.id, patient_id=patient_id
    )
    if existing is not None and existing.split != split:
        raise PatientSplitConflictError(
            f"patient already has a case in split {existing.split!r} within this version — "
            f"cannot also add one in {split!r} (patient-level split integrity)"
        )

    case = dataset_repository.create_case(
        db, dataset_version_id=version.id, patient_id=patient_id, annotation_id=annotation.id, split=split
    )
    audit_repository.record(
        db, user_id=actor.id, action="dataset_case_added", resource_type="dataset_case",
        resource_id=str(case.id), result="success",
        event_metadata={"dataset_version_id": str(version.id), "split": split},
    )
    return case


def _compute_checksum(cases: list[DatasetCase]) -> str:
    lines = sorted(f"{c.patient_id}:{c.annotation_id}:{c.split}" for c in cases)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def lock_version(db: Session, *, actor: User, version: DatasetVersion) -> DatasetVersion:
    if version.status == DatasetVersionStatus.LOCKED.value:
        raise DatasetVersionLockedError("dataset version is already LOCKED")

    cases = dataset_repository.list_cases(db, version.id)
    if not cases:
        raise EmptyDatasetVersionError("cannot lock a dataset version with no cases")

    version.checksum = _compute_checksum(cases)
    version.status = DatasetVersionStatus.LOCKED.value
    version.locked_at = datetime.now(timezone.utc)
    db.flush()
    audit_repository.record(
        db, user_id=actor.id, action="dataset_version_locked", resource_type="dataset_version",
        resource_id=str(version.id), result="success",
        event_metadata={"checksum": version.checksum, "case_count": len(cases)},
    )
    return version
