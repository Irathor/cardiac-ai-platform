# Importing ACDC data

There is no automatic download of the ACDC (Automated Cardiac Diagnosis Challenge) dataset
anywhere in this repository, and there must never be one — see
[`docs/clinical-limitations.md`](clinical-limitations.md). An operator who already has a licensed
copy of the dataset imports it explicitly, case by case, through the same API endpoints a clinician
or annotator would use — there is no separate bulk-import pipeline or script yet.

## Prerequisites

- You have obtained the ACDC dataset yourself, under its own license terms.
- The stack is running (`docker compose up`) and you're authenticated as a user with the
  appropriate role for each step below (see [`docs/permissions.md`](permissions.md)).
- Local raw ACDC files go under `data/acdc-raw/` at the repo root — already excluded by
  `.gitignore` so they're never accidentally committed.

## Per-case import flow

ACDC ships each patient as a folder with 4D cine NIfTI volumes plus ED/ES frame indices and
ground-truth segmentation masks. For each case:

1. **Create the patient and study** (ADMIN) — `POST /patients`, then
   `POST /patients/{id}/studies`. Use a study-level identifier that traces back to the ACDC
   patient folder (e.g. `patient001`) so re-imports are idempotent and auditable — never invent a
   fictitious identity for what is, here, real (anonymized) trial data.
2. **Upload the ED and ES frames as separate ImageSeries** (DOCTOR) —
   `POST /studies/{id}/series` twice, once with `phase=ED` and once with `phase=ES`, extracting
   each frame from the source 4D volume into its own 3D NIfTI file first (nibabel: index the 4th
   dimension at the ED/ES frame number from `Info.cfg`).
3. **Upload the ground-truth mask for each frame as a Segmentation** —
   `POST /series/{id}/segmentations`. ACDC's mask label convention (0=background, 1=RV, 2=myocardium,
   3=LV) already matches `ml.cardiac_ai_ml.labels.CardiacLabels` exactly, so no relabeling is
   needed. This immediately computes real biomarkers (see `docs/data-dictionary.md`).
4. **Turn the ground-truth mask into ground truth** (DOCTOR + ANNOTATOR) — ACDC's masks are
   already expert-verified, so the annotation workflow here is a formality rather than a real
   correction pass: request an annotation against the uploaded segmentation
   (`POST /segmentations/{id}/annotations`), have the assigned ANNOTATOR set `diagnosis_label` to
   the case's ACDC group from `Info.cfg` (`Group` — NOR/MINF/DCM/HCM/RV map directly to
   `cardiac_ai_ml.classification.DiagnosisClass`) and submit, then have a DOCTOR approve it
   (`POST /annotations/{id}/review`). Only an APPROVED annotation can become a dataset case.
5. **Add the case to a dataset version** (ML_ENGINEER) —
   `POST /datasets/{dataset_id}/versions/{version_id}/cases`, using ACDC's own published
   training/testing split (or your own) as the `split` value. Patient-level split integrity is
   enforced automatically (see `docs/data-dictionary.md`).

## What doesn't exist yet

A script that walks an ACDC folder tree and drives steps 1-5 automatically for every case — this
would be a natural Phase 8+ follow-up, but doing it manually through the API above is fully
functional today and was used to write the tests in `backend/tests/test_training_api.py` (with
synthetic, ACDC-shaped biomarker profiles rather than the real dataset, since the real ACDC data
isn't redistributed with this repository).
