"""EPIC-15 (Showcase pedagógico LIME vs. Shapley): both endpoints are
read-only passthroughs over an artifact already generated offline by
ml/scripts/run_explainability_showcase.py — see
docs/epics/EPIC-15-showcase-lime-vs-shapley.md "Contrato técnico". These
tests exercise the real file-reading path against a fixture JSON/PNG
written to a tmp_path data_root, never a mock of app.services.explainability_service.
"""
import json

from tests.conftest import make_user

_SHOWCASE_JSON = {
    "unet_seg_grad_cam": {
        "patient_id": "patient101",
        "slice_index": 5,
        "structures": {
            "LV": {
                "predicted_pixel_count": 1714,
                "layer_name": "model.1.submodule.2.1",
                "attribution_mean": 0.038,
                "attribution_max": 1.0,
                "png_path": "data\\models\\explainability\\unet_gradcam_patient101_LV.png",
            },
        },
    },
    "cnn3d_grad_cam": {
        "patient_id": "patient101",
        "true_class": "DILATED_CARDIOMYOPATHY",
        "predicted_class": "DILATED_CARDIOMYOPATHY",
        "layer_name": "features.3.2",
        "attribution_mean": 0.123,
        "attribution_max": 1.0,
        "png_path": "data\\models\\explainability\\cnn3d_gradcam_patient101_z6.png",
    },
    "lime_shapley_panel": {
        "patient_id": "patient101",
        "predicted_class": "MYOCARDIAL_INFARCTION",
        "method_attributions": {
            "LIME (aproximado)": {"EJECTION_FRACTION": -0.26},
            "Shapley (exacto)": {"EJECTION_FRACTION": 3.81},
        },
        "note": "Panel comparativo pedagogico (ver ADR-3)",
    },
}

_PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-png-bytes-for-test"


def _login(client, email: str, password: str = "Str0ng-Password!") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _patch_data_root(monkeypatch, tmp_path) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "data_root", str(tmp_path))


def _write_showcase_fixture(tmp_path) -> None:
    showcase_dir = tmp_path / "models" / "explainability"
    showcase_dir.mkdir(parents=True)
    (showcase_dir / "explainability_showcase.json").write_text(
        json.dumps(_SHOWCASE_JSON), encoding="utf-8"
    )
    (showcase_dir / "unet_gradcam_patient101_LV.png").write_bytes(_PNG_BYTES)
    (showcase_dir / "cnn3d_gradcam_patient101_z6.png").write_bytes(_PNG_BYTES)


def test_get_showcase_returns_real_json_content(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    make_user(db_session, demo_org, email="ml1@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml1@cardiacai-test.dev")

    response = client.get("/api/v1/explainability/showcase", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert body["unet_seg_grad_cam"]["patient_id"] == "patient101"
    assert body["cnn3d_grad_cam"]["predicted_class"] == "DILATED_CARDIOMYOPATHY"
    assert body["lime_shapley_panel"]["method_attributions"]["LIME (aproximado)"]["EJECTION_FRACTION"] == -0.26
    assert "Shapley (exacto)" in body["lime_shapley_panel"]["method_attributions"]


def test_get_showcase_404s_honestly_when_not_generated(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    # No fixture written — simulates a dev/CI environment where the offline
    # script never ran.
    make_user(db_session, demo_org, email="ml2@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml2@cardiacai-test.dev")

    response = client.get("/api/v1/explainability/showcase", headers=_auth(token))

    assert response.status_code == 404
    assert "run_explainability_showcase.py" in response.json()["detail"]


def test_doctor_cannot_view_showcase(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    make_user(db_session, demo_org, email="doc1@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc1@cardiacai-test.dev")

    response = client.get("/api/v1/explainability/showcase", headers=_auth(token))

    assert response.status_code == 403


def test_get_showcase_requires_authentication(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)

    response = client.get("/api/v1/explainability/showcase")

    assert response.status_code == 401


def test_get_showcase_image_serves_a_real_allowed_file(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    make_user(db_session, demo_org, email="ml3@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml3@cardiacai-test.dev")

    response = client.get(
        "/api/v1/explainability/showcase/images/unet_gradcam_patient101_LV.png", headers=_auth(token)
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == _PNG_BYTES


def test_get_showcase_image_rejects_filename_not_in_json(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    # A file that physically exists on disk (right next to the allowed
    # ones) but isn't referenced by any png_path in the JSON must still be
    # rejected — the allowlist is the JSON, never a directory listing.
    (tmp_path / "models" / "explainability" / "not_in_json.png").write_bytes(_PNG_BYTES)
    make_user(db_session, demo_org, email="ml4@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml4@cardiacai-test.dev")

    response = client.get(
        "/api/v1/explainability/showcase/images/not_in_json.png", headers=_auth(token)
    )

    assert response.status_code == 404


def test_get_showcase_image_rejects_path_traversal(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    # A real secret file outside the showcase dir, to prove traversal never
    # reaches it.
    (tmp_path / "secret.txt").write_text("outside the allowed dir", encoding="utf-8")
    make_user(db_session, demo_org, email="ml5@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml5@cardiacai-test.dev")

    response = client.get(
        "/api/v1/explainability/showcase/images/..%2F..%2Fsecret.txt", headers=_auth(token)
    )

    assert response.status_code == 404


def test_get_showcase_image_rejects_absolute_style_filename_with_separator(
    client, db_session, demo_org, monkeypatch, tmp_path
):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    make_user(db_session, demo_org, email="ml6@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml6@cardiacai-test.dev")

    response = client.get(
        "/api/v1/explainability/showcase/images/models%2Fexplainability%2Funet_gradcam_patient101_LV.png",
        headers=_auth(token),
    )

    assert response.status_code == 404


def test_get_showcase_image_404s_honestly_when_not_generated(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    make_user(db_session, demo_org, email="ml7@cardiacai-test.dev", role="ML_ENGINEER")
    token = _login(client, "ml7@cardiacai-test.dev")

    response = client.get(
        "/api/v1/explainability/showcase/images/unet_gradcam_patient101_LV.png", headers=_auth(token)
    )

    assert response.status_code == 404


def test_doctor_cannot_view_showcase_image(client, db_session, demo_org, monkeypatch, tmp_path):
    _patch_data_root(monkeypatch, tmp_path)
    _write_showcase_fixture(tmp_path)
    make_user(db_session, demo_org, email="doc2@cardiacai-test.dev", role="DOCTOR")
    token = _login(client, "doc2@cardiacai-test.dev")

    response = client.get(
        "/api/v1/explainability/showcase/images/unet_gradcam_patient101_LV.png", headers=_auth(token)
    )

    assert response.status_code == 403
