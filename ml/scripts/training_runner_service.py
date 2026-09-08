"""Host-side bridge the Celery worker (inside Docker) reaches to launch real
GPU training. GPU passthrough into the worker container isn't available on
this deployment, so U-Net/CNN3D training keeps running exactly the way it
already does today — `.venv-dl`, on the host, via train_segmentation.py /
train_classification.py — just triggered over HTTP instead of by hand.

stdlib only, on purpose: this runs outside any project virtualenv management
(it has to be started before `.venv-dl` work even begins), so it can't rely
on anything `pip install`-ed. A single process, one in-memory job dict — if
it restarts, any in-flight job is simply lost and the training run that
launched it fails cleanly (see app.services.training_service.execute_dl_training),
which is an acceptable trade-off for a one-admin-at-a-time internal tool.

Run it with:

    ml/.venv-dl/Scripts/python ml/scripts/training_runner_service.py [--port 8800]

See docs/dl-training-runner.md.
"""
import argparse
import json
import subprocess
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_DIR = REPO_ROOT / "ml"
DATA_ROOT = REPO_ROOT / "data"
ACDC_TRAIN_ROOT = DATA_ROOT / "acdc-raw" / "ACDC" / "database" / "training"
ACDC_TEST_ROOT = DATA_ROOT / "acdc-raw" / "ACDC" / "database" / "testing"
MODELS_ROOT = DATA_ROOT / "models"

# Windows (this deployment) uses Scripts/python.exe; a posix .venv-dl (e.g. CI)
# uses bin/python — support both rather than hardcoding one.
_VENV_DL = ML_DIR / ".venv-dl"
PYTHON = _VENV_DL / "Scripts" / "python.exe" if sys.platform == "win32" else _VENV_DL / "bin" / "python"

_LOG_TAIL_CHARS = 4000

# (module, extra CLI args, result_path relative to DATA_ROOT — a file for
# segmentation, a directory of 3 files for classification, see
# docs/dl-training-runner.md for the exact shapes each one writes).
_JOB_SPECS = {
    "UNET_SEGMENTATION": {
        "module": "cardiac_ai_ml.dl.train_segmentation",
        "args": lambda: [
            "--data-root", str(ACDC_TRAIN_ROOT),
            "--test-root", str(ACDC_TEST_ROOT),
            "--output", str(MODELS_ROOT / "unet2d.pt"),
            "--epochs", "60",
            "--batch-size", "16",
        ],
        "result_path": "models/unet2d.metrics.json",
    },
    "CNN3D_CLASSIFICATION": {
        "module": "cardiac_ai_ml.dl.train_classification",
        "args": lambda: [
            "--data-root", str(ACDC_TRAIN_ROOT),
            "--test-root", str(ACDC_TEST_ROOT),
            "--output-dir", str(MODELS_ROOT / "cnn3d"),
            "--k", "5",
            "--epochs", "60",
        ],
        "result_path": "models/cnn3d",
    },
}

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _run_job(job_id: str, model_type: str) -> None:
    spec = _JOB_SPECS[model_type]
    command = [str(PYTHON), "-u", "-m", spec["module"], *spec["args"]()]

    with _jobs_lock:
        _jobs[job_id]["status"] = "RUNNING"

    try:
        process = subprocess.Popen(
            command, cwd=str(ML_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
    except OSError as exc:
        with _jobs_lock:
            _jobs[job_id]["status"] = "FAILED"
            _jobs[job_id]["error"] = f"failed to launch training process: {exc}"
        return

    log_buffer = ""
    assert process.stdout is not None
    for line in process.stdout:
        log_buffer = (log_buffer + line)[-_LOG_TAIL_CHARS:]
        with _jobs_lock:
            _jobs[job_id]["log_tail"] = log_buffer
    return_code = process.wait()

    with _jobs_lock:
        if return_code == 0:
            _jobs[job_id]["status"] = "COMPLETED"
            _jobs[job_id]["result_path"] = spec["result_path"]
        else:
            _jobs[job_id]["status"] = "FAILED"
            _jobs[job_id]["error"] = f"training process exited with code {return_code} — see log_tail"


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's naming convention
        if urlparse(self.path).path != "/jobs":
            self._send_json(404, {"error": "not found"})
            return

        length = int(self.headers.get("Content-Length", "0"))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid JSON body"})
            return

        model_type = payload.get("model_type")
        if model_type not in _JOB_SPECS:
            self._send_json(400, {"error": f"unknown model_type {model_type!r}, expected one of {list(_JOB_SPECS)}"})
            return

        job_id = str(uuid.uuid4())
        with _jobs_lock:
            _jobs[job_id] = {"status": "QUEUED", "log_tail": "", "result_path": None, "error": None}
        threading.Thread(target=_run_job, args=(job_id, model_type), daemon=True).start()
        self._send_json(200, {"job_id": job_id})

    def do_GET(self) -> None:  # noqa: N802
        parts = urlparse(self.path).path.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "jobs":
            self._send_json(404, {"error": "not found"})
            return

        job_id = parts[1]
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is None:
                self._send_json(404, {"error": "unknown job_id"})
                return
            self._send_json(200, dict(job))

    def log_message(self, format: str, *args) -> None:  # noqa: A002 — matches BaseHTTPRequestHandler's signature
        sys.stderr.write(f"[training-runner] {self.address_string()} - {format % args}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8800)
    args = parser.parse_args()

    if not PYTHON.exists():
        print(f"WARNING: {PYTHON} does not exist yet — set up .venv-dl first (see docs/dl-training-runner.md)", file=sys.stderr)

    # 127.0.0.1 only, matching this project's convention of never exposing a
    # service beyond localhost (see docker-compose.yml) — Docker Desktop's
    # host.docker.internal still reaches a host service bound this way, so
    # the worker container doesn't need this listening on every interface.
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"training runner listening on 127.0.0.1:{args.port} (python: {PYTHON})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
