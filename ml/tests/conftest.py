"""tests/dl/ needs the heavy `dl` extra (torch/monai/nibabel/...) — see
pyproject.toml's comment on that extras group. Skip collecting it entirely
when those aren't installed, so `pip install -e ".[dev]"` (the lightweight,
numpy-only, CI-default install) still runs the rest of the suite instead of
failing to even collect."""
import importlib.util

collect_ignore_glob: list[str] = []
if importlib.util.find_spec("torch") is None:
    collect_ignore_glob.append("dl/*")
