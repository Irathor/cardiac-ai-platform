# Role & permission matrix

> Implemented in `backend/app/core/deps.py` (`require_roles(...)`) as of Phase 2 — see
> `backend/tests/test_permissions.py` for the tests that exercise it by calling the API directly.

Authorization is enforced **exclusively in the backend** (FastAPI dependencies checked on every
route). The frontend hides controls the current role cannot use, purely for usability — that is
never treated as a security boundary, and every rule below must have a corresponding backend test
that manipulates request parameters directly (see `docs/architecture.md#security`).

| Capability | ADMIN | DOCTOR | ANNOTATOR | ML_ENGINEER | MODEL_APPROVER | AUDITOR |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Create/edit/(de)activate users, assign roles | ✅ | | | | | |
| Assign doctors to patients | ✅ | | | | | |
| Manage general configuration | ✅ | | | | | |
| View audit log | ✅ | | | | | ✅ |
| View service/system status | ✅ | | | | | |
| Manage patients/studies (with explicit permission) | ✅ | | | | | |
| View **only assigned** patients | | ✅ | | | | |
| Sort/search/filter patients | | ✅ | | | | |
| View studies, images, segmentations, biomarkers | | ✅ | | | | |
| Request an AI analysis (Phase 5) | ✅ | ✅ | | | | |
| View AI analysis results | | ✅ | | | | |
| Accept/reject a result, set correct diagnosis | | ✅ | | | | |
| Add clinical comments | | ✅ | | | | |
| Send a segmentation for correction | | ✅ | | | | |
| Mark a study as not evaluable | | ✅ | | | | |
| Review a submitted annotation (approve into ground truth / reject) (Phase 6) | | ✅ | | | | |
| View **only assigned** annotation cases | | | ✅ | | | |
| View images/masks, upload corrected mask | | | ✅ | | | |
| Edit allowed clinical labels, save draft | | | ✅ | | | |
| Complete annotation, request review | | | ✅ | | | |
| View anonymized data | | | | ✅ | | |
| Create dataset versions, select approved cases | | | | ✅ | | |
| Configure/start/cancel/supervise training runs (nearest-centroid, U-Net, CNN3D) | ✅ | | | ✅ | | |
| View metrics, artifacts, logs (training runs, model versions, evaluations) | ✅ | | | ✅ | ✅ | |
| Register candidate models, compare models | | | | ✅ | | |
| Review evaluations | | | | | ✅ | |
| Approve/reject candidate models | | | | | ✅ | |
| Promote a validated model to production | | | | | ✅ | |
| Retire a model / roll back to a previous version | | | | | ✅ | |

## Explicit denials (do not infer permission from role seniority)

- **ADMIN cannot activate models** merely by being an administrator — model activation is
  `MODEL_APPROVER`-only, even for an ADMIN account. This is a deliberate, narrow exception to the
  otherwise-strict ADMIN/clinical-and-ML-workflow separation below: ADMIN was added to the
  training-run and model-version/evaluation endpoints (`POST .../training-runs`,
  `GET .../training-runs*`, `GET /model-versions*`) so an administrator can pick a model type and
  retrain it and see the full validation results, without being able to review, approve, promote,
  or retire a model — those stay `MODEL_APPROVER`-only, unchanged.
- **DOCTOR** cannot administer users, and cannot train or activate models.
- **ANNOTATOR** cannot turn their own annotation directly into approved ground truth — it must go
  through the review/approval workflow.
- **ML_ENGINEER** cannot view unnecessary identifying information, and cannot activate a model in
  production directly — only `MODEL_APPROVER` promotes.
- **MODEL_APPROVER** always records a mandatory justification for approval/activation/rollback.
- **AUDITOR** (reserved for a future phase) has read-only access to the audit log — never write
  access to clinical data or models.

## Patient-level isolation for DOCTOR

A DOCTOR's list/detail endpoints filter by their own assignments at the query level. This is
covered by a dedicated backend test that calls the API with another doctor's patient ID directly
(bypassing the UI) and asserts a 404/403, not just that the UI does not show a link to it.
