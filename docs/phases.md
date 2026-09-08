# Implementation phases

Each phase only counts as done once its own tests have been run and passed — see the repo's
top-level [`README.md`](../README.md) for the live status checklist.

1. **Infrastructure** — monorepo, Docker Compose, Postgres, Redis, MinIO, MLflow, backend/frontend
   skeletons, CI, health checks.
2. **Security & users** — authentication, refresh tokens, roles, permissions, sessions, initial
   audit trail, demo users.
3. **Clinical portal** — patients, assignments, studies, search, filters, sorting, patient record,
   study history, clinical reviews.
4. **Imaging & biomarkers** — NIfTI upload, viewer, mask overlay, biomarker calculation, tests
   against synthetic volumes with known ground truth.
5. **Inference** — model interface, Celery worker, asynchronous analysis, explainability
   (SHAP/Grad-CAM), confidence/uncertainty, demo mode.
6. **Annotation & datasets** — annotation workflow, approval to ground truth, dataset versioning,
   checksums, patient-level splits.
7. **Training & MLOps** — training runs via Celery, MLflow tracking, smoke training, candidate
   registration, evaluation, approval, production promotion, rollback.
8. **Quality** — full backend/frontend/e2e test suites, security review, accessibility pass,
   complete documentation, repository cleanup.

## Working rule for every phase

1. Run the tests.
2. Fix what fails.
3. List the files created/changed.
4. Explain how to verify the functionality manually.
5. Update the documentation.
6. Move to the next phase unless there is a real blocker.
