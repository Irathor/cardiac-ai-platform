FROM python:3.12-slim

RUN pip install --no-cache-dir mlflow==2.17.2 psycopg2-binary==2.9.10 boto3==1.35.54

COPY ensure_bucket.py /ensure_bucket.py
COPY start.sh /start.sh
RUN chmod +x /start.sh

RUN useradd --create-home --shell /usr/sbin/nologin mlflowuser
USER mlflowuser

EXPOSE 5000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# ensure_bucket.py creates the MinIO bucket artifacts get logged to — MLflow
# itself has no "ensure bucket" step (see ensure_bucket.py's docstring).
CMD ["/start.sh"]
