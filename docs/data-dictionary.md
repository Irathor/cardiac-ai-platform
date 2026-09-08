# Data dictionary

## Status

Phase 2 through 7 entities are implemented and covered by tests (SQLite in-memory and real
Postgres; see `backend/tests/conftest.py`): `Organization`, `User`, `Role`, `UserRole`,
`RefreshToken`, `AuditEvent`, `Patient`, `PractitionerPatientAssignment`, `ImagingStudy`,
`ClinicalReview`, `ImageSeries`, `Segmentation`, `BiomarkerMeasurement`, `AIAnalysis`,
`Annotation`, `Dataset`, `DatasetVersion`, `DatasetCase`, `TrainingRun`, `ModelVersion`,
`ModelEvaluation`, `ModelApproval`. Everything else below is still just a plan.

`ImagingStudy` has no "model used" / prediction / confidence columns of its own — `AIAnalysis`
rows reference it instead (adding always-null columns before something populates them would
violate the project's "never fabricate a result" rule).

Every entity inherits the shared foundation established in Phase 1:

- `app.db.base.Base` — the SQLAlchemy declarative base all models attach to.
- `app.models.mixins.UUIDPrimaryKeyMixin` — UUID primary key, generated with `uuid4()`.
- `app.models.mixins.TimestampMixin` — timezone-aware `created_at` / `updated_at` (the latter
  auto-updates on write).

Every entity listed below will inherit both mixins, plus a `status` column and, where the spec
calls for soft-delete (Patient, User, ImagingStudy, ModelVersion), a `deleted_at` nullable
timestamp instead of a hard `DELETE` — audited data is never silently destroyed.

## Target entities (implemented incrementally, phase by phase)

| Entity | Introduced in | Notes |
|---|---|---|
| User, Role, UserRole | **Phase 2 (done)** | Argon2 password hash never stored in plaintext logs |
| Organization | **Phase 2 (done)** | |
| RefreshToken | **Phase 2 (done)** | Stores a SHA-256 hash only, never the raw token |
| AuditEvent | **Phase 2 (done)**, extended every phase | Read-only from the application |
| Patient | **Phase 3 (done)** | Soft-delete; fictitious/anonymized data only |
| PractitionerPatientAssignment | **Phase 3 (done)** | Drives DOCTOR-scoped queries |
| ImagingStudy | **Phase 3 (done)**, referenced by Phase 4/5 | Soft-delete; no prediction columns of its own — `AIAnalysis` rows reference it instead, and the patient list's "last prediction"/confidence columns come from a query joining the two rather than denormalizing onto `ImagingStudy` |
| ClinicalReview | **Phase 3 (done)**, extended in Phase 5 | Append-only; `original_prediction` link added once AIAnalysis exists |
| ImageSeries | **Phase 4 (done)** | One uploaded NIfTI volume; `phase` (ED/ES/null) added for future EF pairing |
| Segmentation | **Phase 4 (done)** | `model_version` is null (manual/ground-truth) until Phase 5's real model inference exists |
| Annotation | **Phase 6 (done)** | Draft until submitted for review; DOCTOR approves into ground truth or rejects back to the ANNOTATOR |
| BiomarkerMeasurement | **Phase 4 (done)** | name/value/unit rows, not fixed columns; traces back to the Segmentation it was computed from |
| AIAnalysis | **Phase 5 (done)**, model source changed in Phase 7 | Full per-class probabilities + a denormalized `confidence` column + Shapley feature attributions; `model_version` is `"demo-heuristic-v1"` when no model is in PRODUCTION, else a reference to the promoted `ModelVersion` |
| Dataset, DatasetVersion, DatasetCase | **Phase 6 (done)** | DatasetVersion is immutable once `LOCKED`, stamped with a SHA-256 checksum over its cases; a DatasetCase can only reference an APPROVED Annotation, and patient-level split integrity is enforced (no patient spread across TRAIN/VALIDATION/TEST within one version) |
| TrainingRun | **Phase 7 (done)** | Celery-backed; states QUEUED/RUNNING/COMPLETED/FAILED (CANCELLED is not reachable yet — nothing cancels a running job) |
| ModelVersion | **Phase 7 (done)** | Soft-delete only; never hard-deleted once it has produced analyses. `prototypes` is a JSON copy of the fitted centroids, kept in Postgres so live inference never needs to fetch an MLflow artifact |
| ModelEvaluation, ModelApproval | **Phase 7 (done)** | `ModelApproval.justification` is a required (non-nullable, non-blank-validated) column, not an optional field |
| Notification | Phase 5 / 7 | In-app only, no email/SMS in this version |

This table is the single place that tracks "does X exist yet" — cross-check here before assuming
any entity is queryable.
