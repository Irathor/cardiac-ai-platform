"""app.services.dl_inference_client: the HTTP bridge to the host DL training
runner's real-time inference endpoints (see docs/dl-training-runner.md).
httpx itself is monkeypatched (no host runner in the test environment, same
approach test_training_api.py already uses for /jobs) — but the staging/
cleanup of files on the shared data mount and the base64 mask decoding are
genuinely exercised, not mocked. The "runner truly unreachable" case is
exercised for real (no monkeypatch at all) against a URL nothing listens on.
"""
import base64

import httpx
import numpy as np
import pytest

from app.core.config import get_settings
from app.services import dl_inference_client


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self) -> dict:
        return self._payload


def _patch_data_root(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(get_settings(), "data_root", str(tmp_path))


def test_classify_cnn3d_stages_and_cleans_up_both_files(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    seen_payload = {}

    def fake_post(url, json=None, timeout=None):
        seen_payload.update(json)
        # Both staged files must exist (real bytes on the shared mount) at
        # the moment the runner would read them.
        ed_path = tmp_path / json["ed_relative_path"]
        es_path = tmp_path / json["es_relative_path"]
        assert ed_path.read_bytes() == b"ed-bytes"
        assert es_path.read_bytes() == b"es-bytes"
        return _FakeResponse({"predicted_class": "NORMAL", "probabilities": {"NORMAL": 1.0}})

    monkeypatch.setattr(dl_inference_client.httpx, "post", fake_post)

    result = dl_inference_client.classify_cnn3d(ed_bytes=b"ed-bytes", es_bytes=b"es-bytes")

    # No gradcam_* keys came back on the wire (the runner didn't include
    # them here) — classify_cnn3d treats them as optional, not required.
    assert result == {
        "predicted_class": "NORMAL",
        "probabilities": {"NORMAL": 1.0},
        "gradcam_attribution": None,
        "gradcam_layer_name": None,
        "gradcam_error": None,
    }
    assert seen_payload["ed_relative_path"].startswith("tmp/inference/")
    # Cleaned up after the call returns.
    assert not (tmp_path / seen_payload["ed_relative_path"]).exists()
    assert not (tmp_path / seen_payload["es_relative_path"]).exists()


def test_classify_cnn3d_decodes_gradcam_attribution_when_present(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    attribution = np.random.default_rng(0).random((4, 4, 2)).astype(np.float32)

    def fake_post(url, json=None, timeout=None):
        return _FakeResponse({
            "predicted_class": "NORMAL",
            "probabilities": {"NORMAL": 1.0},
            "gradcam_attribution_base64": base64.b64encode(attribution.tobytes()).decode("ascii"),
            "gradcam_attribution_shape": list(attribution.shape),
            "gradcam_layer_name": "features.3.2",
        })

    monkeypatch.setattr(dl_inference_client.httpx, "post", fake_post)

    result = dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")

    np.testing.assert_allclose(result["gradcam_attribution"], attribution)
    assert result["gradcam_layer_name"] == "features.3.2"
    assert result["gradcam_error"] is None


def test_classify_cnn3d_surfaces_gradcam_error_when_runner_reports_one(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)

    def fake_post(url, json=None, timeout=None):
        return _FakeResponse({
            "predicted_class": "NORMAL",
            "probabilities": {"NORMAL": 1.0},
            "gradcam_error": "layer hook produced a zero gradient",
        })

    monkeypatch.setattr(dl_inference_client.httpx, "post", fake_post)

    result = dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")

    assert result["gradcam_attribution"] is None
    assert result["gradcam_error"] == "layer hook produced a zero gradient"


def test_segment_unet_decodes_base64_mask_and_spacing(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    mask = np.zeros((4, 4, 2), dtype=np.int16)
    mask[0, 0, 0] = 3

    def fake_post(url, json=None, timeout=None):
        return _FakeResponse({
            "mask_base64": base64.b64encode(mask.tobytes()).decode("ascii"),
            "mask_shape": list(mask.shape),
            "voxel_spacing_x_mm": 1.25,
            "voxel_spacing_y_mm": 1.25,
            "voxel_spacing_z_mm": 8.0,
        })

    monkeypatch.setattr(dl_inference_client.httpx, "post", fake_post)

    decoded_mask, sx, sy, sz = dl_inference_client.segment_unet(image_bytes=b"series-bytes")

    np.testing.assert_array_equal(decoded_mask, mask.astype(np.int32))
    assert (sx, sy, sz) == (1.25, 1.25, 8.0)


def test_cleanup_runs_even_when_the_http_call_itself_raises(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)

    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(dl_inference_client.httpx, "post", fake_post)

    with pytest.raises(dl_inference_client.InferenceRunnerError):
        dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")

    staged_dir = tmp_path / "tmp" / "inference"
    assert list(staged_dir.iterdir()) == []


def test_runner_returning_a_non_200_status_raises(monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    monkeypatch.setattr(
        dl_inference_client.httpx, "post", lambda url, json=None, timeout=None: _FakeResponse({"error": "no checkpoint"}, status_code=409)
    )

    with pytest.raises(dl_inference_client.InferenceRunnerError):
        dl_inference_client.segment_unet(image_bytes=b"series-bytes")


def test_real_unreachable_runner_raises_a_clean_error_with_no_mocking(monkeypatch, tmp_path):
    """No httpx monkeypatch here at all — this is the genuine "the host
    runner isn't running" failure mode (docs/dl-training-runner.md's manual
    prerequisite), exercised against a real socket connect."""
    _patch_data_root(monkeypatch, tmp_path)
    monkeypatch.setattr(get_settings(), "training_runner_url", "http://127.0.0.1:1")

    with pytest.raises(dl_inference_client.InferenceRunnerError):
        dl_inference_client.classify_cnn3d(ed_bytes=b"ed", es_bytes=b"es")
