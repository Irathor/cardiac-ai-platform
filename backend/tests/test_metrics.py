"""app.core.metrics: the `observe_inference` context manager wrapping the two
real-time inference paths in app.services.dl_inference_client, and the
`GET /metrics` endpoint that exposes them (see
docs/epics/EPIC-6-monitoring-basico.md).

`DL_INFERENCE_DURATION_SECONDS`/`DL_INFERENCE_REQUESTS_TOTAL` are
module-level singletons registered once, at import time, on
`prometheus_client`'s default global registry — the same instance the
`/metrics` endpoint's `generate_latest()` reads from, and the same instance
every test in this process shares (recreating them per test would mean a
second registration under the same metric name, which prometheus_client
rejects). So instead of resetting the registry between tests, every
assertion here compares a **before/after delta** for the exact
`model_type`/`outcome` label combination it triggered — immune to whatever
value other tests (or import-time module reloads) left behind.
"""
import httpx
import pytest

from app.core.metrics import DL_INFERENCE_DURATION_SECONDS, DL_INFERENCE_REQUESTS_TOTAL
from app.services import dl_inference_client


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def _patch_data_root(monkeypatch, tmp_path) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "data_root", str(tmp_path))


def _requests_total(model_type: str, outcome: str) -> float:
    return DL_INFERENCE_REQUESTS_TOTAL.labels(model_type=model_type, outcome=outcome)._value.get()


def _duration_observation_count(model_type: str) -> float:
    # `collect()` is the public API `generate_latest()` itself uses under the
    # hood — walk its samples for the "_count" series (the number of
    # observations recorded) matching this label, rather than reaching into
    # a private attribute.
    for sample in DL_INFERENCE_DURATION_SECONDS.collect()[0].samples:
        if sample.name.endswith("_count") and sample.labels.get("model_type") == model_type:
            return sample.value
    return 0.0


def test_classify_cnn3d_success_increments_success_counter_and_duration(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    before_success = _requests_total("cnn3d", "success")
    before_failure = _requests_total("cnn3d", "failure")
    before_duration_count = _duration_observation_count("cnn3d")

    monkeypatch.setattr(
        dl_inference_client.httpx,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse(
            {"predicted_class": "NORMAL", "probabilities": {"NORMAL": 1.0}}
        ),
    )

    dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")

    assert _requests_total("cnn3d", "success") == before_success + 1
    assert _requests_total("cnn3d", "failure") == before_failure
    assert _duration_observation_count("cnn3d") == before_duration_count + 1


def test_segment_unet_success_increments_success_counter_and_duration(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    import base64

    import numpy as np

    before_success = _requests_total("unet", "success")
    before_duration_count = _duration_observation_count("unet")

    mask = np.zeros((2, 2, 1), dtype=np.int16)

    monkeypatch.setattr(
        dl_inference_client.httpx,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse(
            {
                "mask_base64": base64.b64encode(mask.tobytes()).decode("ascii"),
                "mask_shape": list(mask.shape),
                "voxel_spacing_x_mm": 1.0,
                "voxel_spacing_y_mm": 1.0,
                "voxel_spacing_z_mm": 1.0,
            }
        ),
    )

    dl_inference_client.segment_unet(image_bytes=b"series-bytes")

    assert _requests_total("unet", "success") == before_success + 1
    assert _duration_observation_count("unet") == before_duration_count + 1


def test_classify_cnn3d_failure_increments_failure_counter_not_success(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    before_success = _requests_total("cnn3d", "success")
    before_failure = _requests_total("cnn3d", "failure")
    before_duration_count = _duration_observation_count("cnn3d")

    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(dl_inference_client.httpx, "post", fake_post)

    with pytest.raises(dl_inference_client.InferenceRunnerError):
        dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")

    assert _requests_total("cnn3d", "failure") == before_failure + 1
    assert _requests_total("cnn3d", "success") == before_success
    # The duration is still recorded for a failed call (it took real wall
    # time before failing) — only the outcome label differs.
    assert _duration_observation_count("cnn3d") == before_duration_count + 1


def test_segment_unet_non_200_response_increments_failure_counter(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    before_failure = _requests_total("unet", "failure")
    before_success = _requests_total("unet", "success")

    monkeypatch.setattr(
        dl_inference_client.httpx,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse({"error": "no checkpoint"}, status_code=409),
    )

    with pytest.raises(dl_inference_client.InferenceRunnerError):
        dl_inference_client.segment_unet(image_bytes=b"series-bytes")

    assert _requests_total("unet", "failure") == before_failure + 1
    assert _requests_total("unet", "success") == before_success


def test_metrics_endpoint_returns_prometheus_format_with_real_data(client, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        dl_inference_client.httpx,
        "post",
        lambda url, json=None, timeout=None: _FakeResponse(
            {"predicted_class": "NORMAL", "probabilities": {"NORMAL": 1.0}}
        ),
    )
    dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "dl_inference_duration_seconds" in body
    assert "dl_inference_requests_total" in body
    assert 'model_type="cnn3d"' in body
    assert 'outcome="success"' in body


def test_metrics_endpoint_is_mounted_at_app_root_not_under_api_v1(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert client.get("/api/v1/metrics").status_code == 404
