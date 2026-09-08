"""Creates the MinIO bucket MLflow logs artifacts to, if it doesn't exist yet.

Unlike app.storage.object_storage.MinioObjectStorage (the clinical backend's
own bucket), nothing else creates this one — MLflow itself has no
"ensure bucket" step, it just fails every artifact upload with NoSuchBucket
if it's missing.
"""
import os

import boto3
from botocore.exceptions import ClientError

artifact_root = os.environ["MLFLOW_ARTIFACT_ROOT"]
assert artifact_root.startswith("s3://"), f"expected an s3:// artifact root, got {artifact_root!r}"
bucket = artifact_root[len("s3://") :].split("/")[0]

client = boto3.client(
    "s3",
    endpoint_url=os.environ["MLFLOW_S3_ENDPOINT_URL"],
    aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
    aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
)

try:
    client.head_bucket(Bucket=bucket)
except ClientError:
    client.create_bucket(Bucket=bucket)
