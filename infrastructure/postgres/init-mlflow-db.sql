-- MLflow manages its own Alembic-versioned schema. It must not share a database
-- with the clinical backend's schema, or the two independent alembic_version
-- tables collide (each service's migrations "can't locate" the other's revision).
CREATE DATABASE mlflow;
