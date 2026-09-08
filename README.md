# CardiacAI Research Platform

**Automated Cardiac MRI Segmentation, Functional Biomarker Extraction and Explainable Disease Classification**

> ⚠️ **Research prototype only. Not validated for clinical diagnosis or treatment decisions.**
> This is a research and demonstration platform. It is not a medical device and must never be used
> to inform real patient care. See [`docs/clinical-limitations.md`](docs/clinical-limitations.md).

## Project status

This repository is being built incrementally, phase by phase (see [`docs/phases.md`](docs/phases.md)).

- [x] **Phase 1 — Infrastructure** (fully verified): monorepo, Docker Compose (Postgres, Redis,
      MinIO, MLflow), backend skeleton with real health checks, frontend skeleton with the
      mandatory disclaimer banner, CI.
  - Frontend: `npm test`, `tsc -b` and `npm run build` actually run and pass.
  - Backend: `pytest` and a real `uvicorn` boot actually run and pass both outside Docker (local
    Python 3.12 venv, `backend/.venv`, in-memory SQLite) and **inside the full `docker compose up`
    stack** against real Postgres/Redis/MinIO — liveness responds over real HTTP, readiness
    genuinely reports `{"database": "ok"}` against a live Postgres connection.
  - Fixed along the way: MLflow's `docker-compose.yml` config pointed its backend store at the
    *same* Postgres database as the clinical backend. MLflow manages its own Alembic-versioned
    schema, so the two collided on a shared `alembic_version` table (each service's migrations
    couldn't locate the other's revision). Fix: MLflow now gets its own `mlflow` database, created
    via `infrastructure/postgres/init-mlflow-db.sql` on first Postgres init. Also added a
    `./backend/tests:/srv/tests` dev bind mount in `docker-compose.yml` — the production Dockerfile
    intentionally doesn't `COPY` the tests directory into the image, so `docker compose exec backend
    pytest` (the README/Makefile's documented primary test path) could never have worked without it.
    Also fixed: MLflow's `docker-compose.yml` healthcheck ran `curl`, which isn't installed in its
    `python:3.12-slim`-based image (only surfaced once MLflow could actually boot far enough to be
    healthchecked at all) — switched it to the same Python `urllib` check the Dockerfile's own
    `HEALTHCHECK` already uses. All 6 services (`postgres`, `redis`, `minio`, `mlflow`, `backend`,
    `frontend`) now report healthy together for the first time.
- [x] **Phase 2 — Security & users** (fully verified): Argon2 password hashing, rotating JWT
      refresh tokens with reuse detection, account lockout after repeated failed logins,
      role-based access control (ADMIN/DOCTOR/ANNOTATOR/ML_ENGINEER/MODEL_APPROVER/AUDITOR), user
      management (create/activate/deactivate/assign roles, ADMIN only), append-only audit log,
      demo-user seed script.
  - 36 backend tests pass both against an in-memory SQLite database (see `backend/app/db/types.py`
    — a portable UUID column type used only to make this possible) and inside the Docker stack
    against real Postgres.
  - `alembic upgrade head` (migration `0001_initial_auth_schema`) and `app/scripts/seed_demo.py`
    have been run against a real Postgres instance and verified.
- [x] **Phase 3 — Clinical portal** (fully verified): patients (create/list/detail/update), doctor
      assignments, imaging studies, append-only clinical reviews. Paginated/searchable/sortable/
      filterable patient list (name/identifier search, study-date range, diagnosis, last-study
      status, "only my patients").
  - 36 backend tests pass against both in-memory SQLite and real Postgres, including the critical
    security test: a DOCTOR cannot see a patient they aren't assigned to even by manipulating
    query parameters directly — verified with a 404 (not 403) so existence isn't leaked either.
  - A clinical review is never overwritten: correcting a diagnosis appends a new
    `ClinicalReview` row, and the full history is retrievable.
  - **Deferred to Phase 5** (needs `AIAnalysis`, which doesn't exist yet): the "predicción más
    reciente", "confianza" and "filtro por confianza baja" columns/filters from the original
    spec's patient screen. Adding them now would mean columns that are always null — see
    `docs/data-dictionary.md`.
  - `alembic upgrade head` (migration `0002_clinical_portal_schema`) has been run against a real
    Postgres instance and verified.
- [x] **Phase 4 — Imaging & biomarkers** (fully verified): NIfTI series upload, storage in MinIO,
      segmentation mask upload, biomarker calculation (LV/RV/myocardial volume, myocardial mass),
      a Niivue-based viewer with mask overlay.
  - New `ml/cardiac_ai_ml` package (see `docs/architecture.md` — no FastAPI/Celery imports, plain
    numpy in/out) computes biomarkers from a voxel label mask using the ACDC label convention
    (background/RV/myocardium/LV). 12 tests against synthetic volumes with known ground truth: an
    axis-aligned block (exact volume, no discretization error) and a sphere (checked against the
    analytic `4/3 * pi * r^3` formula within 3% — voxel-counting a curved surface can't be exact).
  - New entities `ImageSeries`, `Segmentation`, `BiomarkerMeasurement` (migration
    `0003_imaging_phase4_schema`, run and verified against real Postgres). Biomarkers are
    name/value/unit rows rather than fixed columns, so adding a new biomarker later never needs a
    migration that leaves existing rows with an always-null column.
  - New `app/storage/object_storage.py` (thin boto3/MinIO wrapper) — the frontend still never
    talks to MinIO directly, only through backend endpoints that stream the bytes through.
  - 6 new backend API tests (upload/list/download roundtrip/shape-mismatch rejection/invalid-file
    rejection) pass against both SQLite (fake in-memory storage) and real Postgres; a full
    real-Postgres+real-MinIO smoke run (login → patient → assignment → study → series upload →
    segmentation upload → biomarkers → file download byte-for-byte roundtrip) was run manually and
    passed.
  - Fixed along the way: `docker compose exec backend pytest` needs `backend/tests/` inside the
    container (see Phase 1 note above) and the ml/ package needs installing before the backend —
    the backend build context moved to the repo root (`docker-compose.yml`) so its Dockerfile can
    `COPY ml` and `pip install -e /ml` ahead of the backend's own install.
  - Frontend: new `NiftiViewer` component (Niivue, mask rendered as a translucent red overlay) and
    a minimal `/viewer` demo page (login form + study/series picker) — the frontend had no
    login UI or patient/study screens at all yet (it was still the Phase 1 skeleton despite the
    backend having reached Phase 3), so this page owns its own login rather than depending on
    infrastructure that doesn't exist. `npm test`, `tsc -b` and `npm run build` pass; the built
    bundle was confirmed served correctly from the running `frontend` container and does contain
    the Niivue code (grepped for `Niivue`/`loadVolumes` in the served JS). **Not verified**: actual
    interactive use in a real browser — there's no browser automation tool available in this
    session, so `NiftiViewer` is only verified via a mocked-Niivue unit test (jsdom has no WebGL)
    plus the confirmation that the real API calls it depends on work end-to-end. Open the app and
    click through `/viewer` manually to confirm the on-screen rendering before relying on it.
  - Ejection fraction (needs a paired ED/ES segmentation, using the `phase` column on
    `ImageSeries`) is computed in Phase 5, where it's actually consumed. BSA-indexed volumes
    (needs `Patient.height_cm`/`weight_kg`) are still deferred — a natural follow-up, not done
    here to keep scope to what's actually built and tested.
- [x] **Phase 5 — Inference** (fully verified): async disease classification via a real Celery
      worker, full per-class probabilities, exact Shapley-value explainability, confidence, and a
      demo mode — since no trained model exists yet (that's Phase 7), all of this runs against a
      clearly-labeled heuristic classifier rather than pretending to have one.
  - New `ml/cardiac_ai_ml/classification.py`: a nearest-prototype classifier over 4 biomarkers
    (ejection fraction, LV/RV end-diastolic volume, myocardial mass) against 5 illustrative,
    hand-picked profiles loosely inspired by the ACDC challenge's diagnostic categories — **not**
    derived from real training data, **not** clinically validated (see
    `docs/clinical-limitations.md`). Softmax over negative squared distance gives real per-class
    probabilities. 12 new tests (24 total in `ml/`), including that each prototype classifies as
    itself and that Shapley values satisfy the efficiency and symmetry axioms.
  - Explainability is genuine exact Shapley values (brute-force over all 16 feature-subset
    coalitions — tractable at 4 features), not a placeholder. Grad-CAM is **not** implemented: it
    needs a real CNN's activation maps, which can't exist before Phase 7 trains one — faking it
    would violate this project's "never fabricate a result" rule.
  - New `AIAnalysis` entity (migration `0004_ai_analysis_schema`): status (QUEUED/RUNNING/
    COMPLETED/FAILED), the exact feature values used, full probabilities, a denormalized
    `confidence` column (kept alongside `probabilities` so the patient list's low-confidence
    filter can do a plain `WHERE confidence < x` instead of a per-dialect JSON key lookup),
    Shapley feature attributions, and an error message on failure (e.g. a study missing its ED or
    ES segmentation).
  - New `app/celery_app.py` + `app/tasks/analysis_tasks.py` + a new `worker` service in
    `docker-compose.yml` sharing the backend's image. The request/response path
    (`app.services.analysis_service.create_analysis`) only ever writes a QUEUED row and enqueues
    — it never imports `ml/`; only the Celery task does, per `docs/architecture.md`. Verified with
    a real separate worker container (not eager/in-process mode): `docker compose logs worker`
    shows it actually receiving and completing the task over Redis. Tests run the task eagerly
    in-process (`celery_app.conf.task_always_eager`) against the same SQLite test engine so no
    Redis is needed for `pytest`.
  - New endpoints: `POST /studies/{id}/analyses` (202, always returns QUEUED — real async
    semantics, not "finish it and pretend"), `GET /studies/{id}/analyses`, `GET /analyses/{id}`
    for polling. Same DOCTOR-must-be-assigned rule as studies/series/segmentations. 5 new backend
    tests (happy path, a differently-shaped biomarker profile actually changes the classification,
    listing, graceful failure without ED/ES data, unassigned-doctor 404) — 53 backend tests total,
    passing against both SQLite and real Postgres+Redis+a real worker.
  - Patient list: added the `last_analysis_predicted_class` / `last_analysis_confidence` columns
    and the `low_confidence` filter that Phase 3's README note said were deferred until
    `AIAnalysis` existed (below `LOW_CONFIDENCE_THRESHOLD = 0.6`, see
    `patient_repository.py`) — the "filtro por confianza baja" from the original spec.
  - Who can trigger an analysis isn't explicit in `docs/permissions.md` (only "View AI analysis
    results | DOCTOR" is listed); this implementation allows ADMIN/DOCTOR, matching the existing
    series/segmentation-upload roles — flag if that should be different.
  - Frontend: the `/viewer` page gained a "Run AI analysis" button that polls until completion and
    shows the predicted class, all class probabilities, and the Shapley feature attributions.
    `npm test`, `tsc -b` and `npm run build` pass; same browser-testing caveat as Phase 4 applies
    (no browser automation tool in this session — verified via the real API pipeline and a mocked
    unit test, not by clicking through it).
- [x] **Phase 6 — Annotation & datasets** (fully verified, backend only — see frontend note below):
      annotation workflow from draft to ground truth, dataset versioning with patient-level splits
      and checksums.
  - New `Annotation` entity (migration `0005_annotation_dataset_schema`): a DOCTOR sends a
    Segmentation for correction to a specific ANNOTATOR (`POST /segmentations/{id}/annotations`);
    the ANNOTATOR edits a DRAFT — a diagnosis label (validated against the same 5 classes
    `cardiac_ai_ml.classification.DiagnosisClass` uses, for consistency with what a future trained
    model would predict) and/or an uploaded corrected mask (reuses
    `imaging_service.upload_segmentation`, so it becomes an ordinary `Segmentation` row with
    `model_version="manual-correction"`, biomarkers computed the same way as any other) — then
    submits it; a DOCTOR reviews a SUBMITTED annotation into APPROVED (ground truth) or REJECTED
    (back to the annotator, with a comment). An ANNOTATOR only ever sees/edits cases assigned to
    them; a DOCTOR only ever sees annotations for patients they can already see — same
    non-disclosure convention as everywhere else in this codebase.
  - `docs/permissions.md` didn't say who reviews an annotation (only that ANNOTATOR "cannot turn
    their own annotation directly into approved ground truth"). This implementation has the
    requesting-context DOCTOR review it, mirroring the existing "Send a segmentation for
    correction | DOCTOR" row and the generic "Accept/reject a result, set correct diagnosis |
    DOCTOR" row — flag if that should instead be a different role.
  - New `Dataset` / `DatasetVersion` / `DatasetCase` entities (ML_ENGINEER only): a `DatasetVersion`
    starts DRAFT, cases can only reference an APPROVED annotation, and adding a case enforces
    patient-level split integrity — the same patient can never end up with cases in two different
    splits (TRAIN/VALIDATION/TEST) within one version, which is checked with a plain query against
    a `patient_id` denormalized onto `DatasetCase` specifically to make that check cheap. Locking a
    version stamps it with a SHA-256 checksum over the sorted (patient, annotation, split) triples
    of every case and makes it immutable — no more cases can be added afterward.
  - 17 new backend tests (9 annotation-workflow, 8 dataset-versioning, including the patient-split
    conflict and its "same patient, same split is fine" counterpart) — 65 backend tests total,
    passing against both SQLite and real Postgres. A full real-Postgres+real-MinIO smoke run
    (segmentation → request annotation → draft → submit → approve → create dataset → add case →
    lock, with a real checksum coming back) was run manually and passed.
  - **Frontend: not done this phase.** Annotation and dataset management are backend-only for now
    — no UI was added to `/viewer` or elsewhere for the ANNOTATOR/ML_ENGINEER workflows. The
    frontend already lagged behind the backend by design (see the Phase 4/5 notes above); adding
    three more role-specific screens (annotation review queue, dataset builder) in the same pass
    as the backend would have meant less scrutiny on both. Swagger UI (`/docs`) is the way to
    exercise these endpoints manually for now.
- [x] **Phase 7 — Training & MLOps** (fully verified): a real "smoke training" job over Celery,
      real MLflow run tracking, a candidate model lifecycle (review → approve/reject → promote →
      rollback), and — the capstone — live inference now uses a promoted model automatically
      instead of the Phase 5 demo heuristic.
  - New `ml.cardiac_ai_ml.training.fit_nearest_centroid`: a genuine, well-known algorithm
    (nearest-centroid classifier) — each class's prototype becomes the *real* mean feature vector
    of its TRAIN-split cases, computed from actual annotated data instead of the hand-picked
    profiles `classify_demo` uses. Deliberately lightweight ("smoke training", per
    `docs/phases.md`) rather than a deep-learning pipeline this environment has no imaging
    data/GPU to run — but the algorithm itself is real, not a stand-in. `classify_with_prototypes`
    (refactored out of `classify_demo`) is what both the demo heuristic and a trained model
    ultimately call, so they're interchangeable everywhere downstream. 7 new `ml/` tests
    (31 total), including the efficiency/symmetry-axiom-style checks used for Shapley values.
  - New `TrainingRun`, `ModelVersion`, `ModelEvaluation`, `ModelApproval` entities (migration
    `0006_training_mlops_schema`). A training run reuses `analysis_service.collect_features` for
    every case (excluding — and counting — any whose underlying study lacks a usable ED+ES pair),
    so training and live inference are always evaluated on the exact same feature space, never a
    training-only shortcut. `ModelVersion.prototypes` is a JSON copy of what got logged to MLflow,
    kept in Postgres so a live analysis request never needs to fetch an MLflow artifact (see
    `docs/architecture.md`).
  - New `app/tasks/training_tasks.py` + Celery, same QUEUED-then-enqueue split as Phase 5's
    analysis pipeline. Verified with a real, separate `worker` container (not eager mode):
    dataset → locked version → training run → real MLflow run logged over HTTP → model version →
    evaluation → approve (mandatory justification, `docs/permissions.md`) → promote to
    PRODUCTION, all run manually end to end against real Postgres/Redis/MLflow/MinIO.
  - **The full circle**: `analysis_service.execute_analysis` now checks for a PRODUCTION
    `ModelVersion` and uses its prototypes (and Shapley-explains against them) instead of the demo
    heuristic when one exists — verified with a dedicated test
    (`test_analysis_uses_the_production_model_when_one_exists`) where a promoted model's prototype
    deliberately disagrees with the demo heuristic's, and the API result follows the promoted
    model.
  - Fixed along the way: MLflow's artifact bucket (`s3://mlflow-artifacts` in MinIO) was never
    created by anything — unlike the backend's own `MinioObjectStorage`, MLflow has no
    "ensure bucket" step and just fails every artifact upload with `NoSuchBucket`. New
    `infrastructure/mlflow/ensure_bucket.py` + `start.sh` create it before the server starts.
    Also hardened `training_service.execute_training` to always resolve a run to
    COMPLETED/FAILED (catching any exception, not just the two expected ones) instead of leaving
    it RUNNING forever or crashing the request/worker on an unexpected error — the bucket bug is
    exactly the kind of failure this should have degraded gracefully from in the first place.
  - 11 new backend tests (4 training, 7 model governance) plus the 1 full-circle analysis test —
    89 backend tests total, passing against both SQLite (local file-backed MLflow store) and real
    Postgres/Redis/a real worker/a real MLflow server.
  - **Frontend: not done this phase**, same reasoning as Phase 6 — ML_ENGINEER/MODEL_APPROVER are
    internal MLOps roles, not part of the `/viewer` clinical demo page, and Swagger UI (`/docs`)
    already exercises every endpoint here.
- [x] **Phase 8 — Quality** (fully verified): lint across every package, a real e2e suite, a
      hands-on security review with concrete fixes (not just a report), an accessibility pass, and
      documentation cleanup.
  - **Repository**: the project had never been under version control — initialized git and made
    the first commit here. `git status`/`git log` are now meaningful for the first time.
  - **Lint, for real this time**: `ruff` (`ml`, `backend`) and `eslint` (`frontend`) existed in the
    repo since Phase 1 but neither had ever actually been run — CI never called them, and running
    them cold surfaced real issues: ESLint's config was missing `languageOptions.globals` entirely,
    so *every* browser global (`fetch`, `Blob`, `URL`, `document`, `setTimeout`, ...) was flagged
    `no-undef` across the whole frontend (fixed with the `globals` package); a handful of unused
    imports/variables in `ml/` and `backend/tests/`. Both linters now run in CI on every push.
  - **Security review** (`docs/permissions.md`'s "backend enforces every rule" ethos extended to
    infra/deps):
    - **Unrestricted upload size (OWASP API4:2023)**: the NIfTI/mask upload endpoints did
      `await file.read()` with no cap — an authenticated DOCTOR/ANNOTATOR could exhaust server
      memory or MinIO storage with an arbitrarily large file. Fixed with
      `app/core/uploads.py::read_upload_within_limit` (200 MB, reads in 1 MB chunks and aborts as
      soon as the cap is exceeded, so memory usage is actually bounded, not just checked after the
      fact) — returns `413`. 4 new unit tests + 1 API-level test.
    - **`JWT_SECRET_KEY` had no validation**: an unset value silently defaulted to `""` — `jwt.encode`/
      `decode` "work" fine with an empty secret, meaning anyone could forge a valid access token,
      and nothing would fail loudly to reveal the misconfiguration (unlike `POSTGRES_PASSWORD`/
      `MINIO_*`, which fail immediately and obviously the moment a real connection is attempted).
      Added a pydantic `field_validator` that refuses to start with an empty secret. 3 new tests.
    - **All Docker Compose ports were published to every network interface** (`0.0.0.0`), not just
      localhost — including **Redis with no authentication at all**. Every documented usage in this
      README only ever references `localhost`, so there was no reason for LAN-wide exposure.
      Rebound every port (`postgres`, `redis`, `minio` ×2, `mlflow`, `backend`, `frontend`) to
      `127.0.0.1` only.
    - **Dependency audit**: `npm audit` found 7 frontend vulnerabilities (5 moderate, 1 high, 1
      critical) — `react-router-dom` and the `vite`/`vitest`/`esbuild` chain. Upgraded
      `react-router-dom` 6→7 and `vite`/`vitest` 5→8/2→3 (both needed a major bump — the fixes
      were never backported to the installed major lines); verified the full lint/type-check/test/
      build pipeline still passes after each, then kept them. **0 vulnerabilities now.**
      `pip-audit` on the backend found `starlette` CVEs (fixed by pinning `starlette>=0.47.2` — the
      installed range was capped below the patch by an unrelated `fastapi<0.116` pin, widened to
      `<0.119`) and reviewed the handful that remain unpatchable within `fastapi`'s compatible
      range: all require `StaticFiles`, `FileResponse`, `HTTPEndpoint`, `application/x-www-form-
      urlencoded` forms, or trusting `request.url` for security decisions — this codebase uses none
      of those (checked directly), so they're not exploitable here. `mlflow` (2.x → dozens of CVEs
      only patched in 3.x) and `ecdsa` (a hard dependency of `python-jose` we never actually
      exercise — this API only ever signs HS256, not ECDSA) are documented, deliberately deferred
      residual risks rather than silently ignored — a Phase 7-scale MLflow major-version migration
      wasn't attempted in the same pass as everything else here.
    - **Timing side-channel in login** (noted, not fixed): `authenticate()` already returns an
      identical response for "unknown email" and "wrong password" (no enumeration via response
      content — this was already correct from Phase 2), but skips the Argon2 hash entirely for an
      unknown email, which is measurably faster than hashing-then-rejecting a known email's wrong
      password. A real fix (hash a dummy value for unknown emails to normalize timing) is a
      reasonable follow-up; flagged here rather than either silently fixed or silently ignored.
  - **Frontend test coverage**: `App.tsx` (routing, the backend-status chip, disclaimer banner) and
    `ImagingViewerPage.tsx` (the actual functional page — login, series list, viewer, biomarkers,
    AI analysis request/poll/result) had zero tests before this phase despite being the two most
    important frontend files. 12 new tests (5 + 7), all API calls mocked at the module level. 23
    frontend unit tests total.
  - **E2E tests, from nothing**: `tests/` was documented in this README's repository layout since
    Phase 1 but never actually contained anything. Added a real Playwright suite (`tests/e2e/`)
    that runs against the actual `docker compose up` stack — no mocks — including a real login
    against the real backend/Postgres using the seeded demo doctor. New CI job builds the full
    stack, waits for readiness, seeds demo data, and runs it on every push.
  - **Accessibility**: `<html lang="es">` didn't match the app's actual (English) UI text — fixed
    to `lang="en"`. The NiftiViewer's bare `<canvas>` had no accessible name for screen readers —
    added `role="img"` + a descriptive `aria-label`. MUI's own defaults already covered form labels
    and alert roles correctly (verified via `getByLabelText`/`getByRole` passing in tests, not just
    assumed).
  - **Documentation**: `docs/clinical-limitations.md` linked to `docs/acdc-import.md`, which never
    existed — wrote it, documenting the real (currently manual, API-driven) case-by-case import
    flow rather than pretending a bulk-import script exists. Fixed the repository layout's
    description of `ml/` (said "PyTorch/MONAI"; it's plain numpy) and `scripts/` (described as
    already containing operational scripts; it's an empty placeholder).
  - Everything above is exercised together, one more time, at the very end of this phase: 31 `ml/`
    tests, 85 backend tests (SQLite and real Postgres/Redis/worker/MLflow), 23 frontend unit tests,
    and 4 real Playwright e2e tests against the rebuilt, still-7-services-healthy stack — all
    green, lint clean everywhere, `npm audit`/`pip-audit` reviewed and either fixed or explicitly
    documented as accepted/deferred.

Anything not checked above does not exist in the codebase yet — this README will be updated as each
phase lands, and no phase is marked done until its own tests have actually been run.

## Prerequisites

- Docker Desktop (with Compose v2) — WSL2 backend on Windows
- Node.js 20+ (for local frontend development outside Docker)
- Python 3.12 (for local backend development outside Docker)

## Quickstart

```bash
cp .env.example .env
# edit .env: set POSTGRES_PASSWORD, MINIO_ACCESS_KEY, MINIO_SECRET_KEY, JWT_SECRET_KEY
docker compose up --build
```

Once containers are healthy:

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend API (Swagger/OpenAPI) | http://localhost:8000/docs |
| Backend health (liveness) | http://localhost:8000/api/v1/health/live |
| Backend health (readiness, checks DB) | http://localhost:8000/api/v1/health/ready |
| MLflow | http://localhost:5000 |
| MinIO console | http://localhost:9001 |

Run migrations and seed demo data with `make migrate` / `make seed` (or the equivalent
`docker compose exec backend ...` commands from the Makefile).

## Running tests

```bash
# ml/ — pure biomarker math, no Docker or Postgres needed
cd ml && py -3.12 -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest

# Backend — inside the container (preferred, matches production Python 3.12)
docker compose exec backend pytest

# Backend — local venv alternative when Docker isn't available
# (runs the full suite against an in-memory SQLite database instead of real Postgres;
# install the ml/ package into the same venv first since the backend depends on it)
cd backend && py -3.12 -m venv .venv
.venv/Scripts/pip install -e ../ml && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/python -m pytest

# Frontend
cd frontend && npm test        # unit tests (Vitest)
cd frontend && npm run lint    # ESLint
cd frontend && npx tsc -b      # type-check
cd frontend && npm run build   # production build

# End-to-end (Playwright) — needs the full stack already running (docker compose up)
cd tests && npm install && npx playwright install --with-deps chromium
cd tests && npm test
```

Lint (`ruff check .` for `ml`/`backend`, `npm run lint` for `frontend`) also runs in CI — see
`.github/workflows/ci.yml`.

## Repository layout

```text
cardiac-ai-platform/
├── frontend/        React + TypeScript + Vite + MUI — clinical UI
├── backend/         FastAPI + SQLAlchemy + Alembic — clinical API
├── ml/              Pure numpy — biomarkers, classification, Shapley explainability, "smoke training"
├── infrastructure/  Auxiliary service images (MLflow, ...)
├── scripts/         Reserved for future operational scripts — empty for now; see docs/acdc-import.md
├── docs/            Architecture, permissions, data dictionary, ML/clinical docs
├── tests/           Cross-cutting/e2e tests (Playwright) — needs the full stack running
├── docker-compose.yml
├── .env.example
├── Makefile
└── LICENSE
```

See [`docs/architecture.md`](docs/architecture.md) for the full architecture and
[`docs/permissions.md`](docs/permissions.md) for the role/permission matrix.

## License

Apache License 2.0 — see [`LICENSE`](LICENSE). This is a default choice for a research prototype;
confirm it matches your institution's requirements before any public release.
