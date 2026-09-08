# Clinical limitations

**CardiacAI Research Platform is a research prototype. It is not a medical device and has not
been validated for clinical diagnosis or treatment decisions.** Every screen in the application
carries this disclaimer permanently; it must never be presented as dismissible or optional.

## Scope of what the platform can demonstrate

- Segmentation of the left ventricle, right ventricle and myocardium on cardiac MRI (short-axis,
  ED/ES phases), using the public ACDC dataset structure as a reference.
- Calculation of standard functional biomarkers (volumes, ejection fraction, myocardial mass) from
  those segmentations.
- Classification into the five ACDC diagnostic groups (NOR, MINF, DCM, HCM, RV) as a research
  exercise in explainable classification.

## Explicit non-goals

- **This platform must never be described as a validated "early detection" tool.** Nothing here has
  gone through clinical validation, regulatory review, or prospective evaluation.
- **The ACDC dataset supports experimenting with segmentation and diagnostic classification at a
  single point in time. It does not support, and must never be used to claim, longitudinal
  prediction of future disease progression.**
- No real, identifiable patient data is used anywhere in this repository or its demo data. All
  demo patients are fictitious; ACDC data, when used, is the publicly released anonymized research
  dataset, imported explicitly by an operator (see `docs/acdc-import.md`) — never downloaded
  automatically.
- Model predictions are never fabricated. Until a real model has been trained and registered, any
  result the UI shows is either labelled "model not available" or is an explicitly and
  unambiguously marked **simulated/demo** prediction.
- SHAP and Grad-CAM outputs are exploratory model-introspection tools, not clinical explanations.
  They are always presented alongside this caveat, never as a stand-alone justification for a
  diagnosis.

## Data separation

Fictitious identifying data (patient demographics created for the demo) is always modeled and
stored separately from imaging binary data (NIfTI volumes in object storage), so the two can be
governed, retained, and purged independently.
