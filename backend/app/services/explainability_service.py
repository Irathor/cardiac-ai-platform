"""Serves the LIME-vs-Shapley showcase artifact already generated offline by
ml/scripts/run_explainability_showcase.py (EPIC-1) — see
docs/epics/EPIC-15-showcase-lime-vs-shapley.md "Contrato técnico". Nothing
here recalculates LIME/Shapley/Grad-CAM: this module only reads
data/models/explainability/explainability_showcase.json and the PNGs it
references, and serves them read-only.
"""
import json
import re
from pathlib import Path

# ml/scripts/run_explainability_showcase.py (EPIC-1) is routinely run on a
# Windows dev host (see docs/dl-training-runner.md — the GPU runner lives on
# the host, not in a container) and writes `png_path` with whatever
# separator that host's `pathlib.Path` uses, i.e. backslashes on Windows.
# This service always runs on Linux (the `backend` container), where
# `pathlib.PurePosixPath`/`Path` does NOT treat "\\" as a separator, so a
# plain `Path(png_path).name` silently returns the whole
# "data\\models\\explainability\\foo.png" string instead of "foo.png" —
# found via a real end-to-end check against the real showcase JSON
# generated on this Windows host, not a hypothetical. Split on both
# separators explicitly instead of trusting the host OS's path semantics.
_PATH_SEPARATORS = re.compile(r"[\\/]")


def _basename(path_str: str) -> str:
    return _PATH_SEPARATORS.split(path_str)[-1]

SHOWCASE_NOT_GENERATED_DETAIL = (
    "Explainability showcase not generated in this environment. "
    "Run ml/scripts/run_explainability_showcase.py first."
)


class ShowcaseNotGeneratedError(Exception):
    """Raised when explainability_showcase.json doesn't exist in this
    environment (offline script never ran — e.g. a GPU-less CI/dev box)."""


class ImageNotAllowedError(Exception):
    """Raised when the requested filename isn't exactly one of the
    png_path basenames present in the currently-loaded showcase JSON."""


def _showcase_dir(data_root: str) -> Path:
    return Path(data_root) / "models" / "explainability"


def _showcase_json_path(data_root: str) -> Path:
    return _showcase_dir(data_root) / "explainability_showcase.json"


def load_showcase(data_root: str) -> dict:
    """Reads explainability_showcase.json verbatim (passthrough, no
    recalculation, no reshaping)."""
    path = _showcase_json_path(data_root)
    if not path.is_file():
        raise ShowcaseNotGeneratedError(SHOWCASE_NOT_GENERATED_DETAIL)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _allowed_image_basenames(showcase: dict) -> set[str]:
    """Collects every png_path basename referenced by the currently-loaded
    showcase JSON — the allowlist for /images/{filename} (EPIC-15 "Contrato
    técnico" point 4). Never derived from directory listing: only paths the
    JSON itself vouches for are servable."""
    basenames: set[str] = set()

    structures = showcase.get("unet_seg_grad_cam", {}).get("structures", {})
    for structure in structures.values():
        png_path = structure.get("png_path")
        if png_path:
            basenames.add(_basename(png_path))

    cnn3d_png_path = showcase.get("cnn3d_grad_cam", {}).get("png_path")
    if cnn3d_png_path:
        basenames.add(_basename(cnn3d_png_path))

    return basenames


def load_showcase_image_bytes(data_root: str, filename: str) -> bytes:
    """Validates `filename` against the allowlist of basenames present in
    the JSON, then reads the file. Two independent guardrails, per the
    Epic's "Contrato técnico" point 4:

    1. `filename` must contain no path separator and no `..` segment —
       rejected outright even if it would coincidentally match an allowed
       basename, so a traversal attempt never even reaches the allowlist
       check.
    2. `filename` must match exactly one of the basenames collected from
       the loaded JSON's `png_path` entries — never a directory listing,
       never a client-controlled path concatenated straight to disk.
    """
    if "/" in filename or "\\" in filename or ".." in filename:
        raise ImageNotAllowedError(filename)

    showcase = load_showcase(data_root)
    allowed = _allowed_image_basenames(showcase)
    if filename not in allowed:
        raise ImageNotAllowedError(filename)

    image_path = _showcase_dir(data_root) / filename
    # Belt-and-suspenders: confirm the resolved path still lives inside the
    # showcase directory before reading it, even though the checks above
    # already make that guaranteed.
    showcase_dir_resolved = _showcase_dir(data_root).resolve()
    resolved = image_path.resolve()
    if showcase_dir_resolved not in resolved.parents and resolved != showcase_dir_resolved:
        raise ImageNotAllowedError(filename)

    if not image_path.is_file():
        raise ImageNotAllowedError(filename)

    return image_path.read_bytes()
