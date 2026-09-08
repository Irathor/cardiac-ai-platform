"""Single shared constant so app.services.analysis_service (live inference)
and app.services.training_service (produces new candidates) agree on which
model "name" the one production classifier lives under, without importing
each other (training_service already imports analysis_service.collect_features,
so the reverse import would be circular)."""
MODEL_NAME = "cardiac-classifier"

# The two deep-learning model types (see app.services.training_service.execute_dl_training,
# docs/dl-training-runner.md) — kept separate from MODEL_NAME since they're genuinely different
# artifacts (a U-Net checkpoint / a CNN3D checkpoint, not a prototypes dict) that never feed the
# live nearest-centroid inference path in analysis_service.
MODEL_NAME_UNET = "cardiac-segmentation-unet"
MODEL_NAME_CNN3D = "cardiac-classifier-cnn3d"
