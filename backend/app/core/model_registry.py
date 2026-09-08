"""Single shared constant so app.services.analysis_service (live inference)
and app.services.training_service (produces new candidates) agree on which
model "name" the one production classifier lives under, without importing
each other (training_service already imports analysis_service.collect_features,
so the reverse import would be circular)."""
MODEL_NAME = "cardiac-classifier"
