"""ACDC dataset discovery — reads real files placed at data/acdc-raw/ (see
docs/acdc-import.md); never downloads or fabricates anything itself.

ACDC's per-patient Info.cfg is a plain "Key: value" text file with (at
least) ED, ES, Group, Height, Weight, NbFrame — see the official dataset
documentation. Label convention in every *_gt.nii.gz mask: 0=background,
1=right ventricle cavity, 2=myocardium, 3=left ventricle cavity — this
already matches cardiac_ai_ml.labels.CardiacLabels exactly.
"""
from dataclasses import dataclass
from pathlib import Path

# ACDC's 5 diagnostic groups -> this project's DiagnosisClass taxonomy
# (cardiac_ai_ml.classification), used identically since Phase 5/7's demo
# and trained-nearest-centroid classifiers.
GROUP_TO_DIAGNOSIS_CLASS = {
    "NOR": "NORMAL",
    "MINF": "MYOCARDIAL_INFARCTION",
    "DCM": "DILATED_CARDIOMYOPATHY",
    "HCM": "HYPERTROPHIC_CARDIOMYOPATHY",
    "RV": "ABNORMAL_RIGHT_VENTRICLE",
}


def _parse_info_cfg(path: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        info[key.strip()] = value.strip()
    return info


@dataclass(frozen=True)
class AcdcPatient:
    patient_id: str
    directory: Path
    ed_frame: int
    es_frame: int
    group: str
    height_cm: float | None
    weight_kg: float | None
    nb_frame: int

    @property
    def diagnosis_class(self) -> str:
        return GROUP_TO_DIAGNOSIS_CLASS[self.group]

    @property
    def ed_image_path(self) -> Path:
        return self.directory / f"{self.patient_id}_frame{self.ed_frame:02d}.nii.gz"

    @property
    def ed_mask_path(self) -> Path:
        return self.directory / f"{self.patient_id}_frame{self.ed_frame:02d}_gt.nii.gz"

    @property
    def es_image_path(self) -> Path:
        return self.directory / f"{self.patient_id}_frame{self.es_frame:02d}.nii.gz"

    @property
    def es_mask_path(self) -> Path:
        return self.directory / f"{self.patient_id}_frame{self.es_frame:02d}_gt.nii.gz"

    @property
    def four_d_path(self) -> Path:
        return self.directory / f"{self.patient_id}_4d.nii.gz"

    def frame_image_paths(self) -> list[tuple[str, Path, Path]]:
        """[(phase, image_path, mask_path), ...] for ED and ES."""
        return [
            ("ED", self.ed_image_path, self.ed_mask_path),
            ("ES", self.es_image_path, self.es_mask_path),
        ]


class MissingAcdcDataError(FileNotFoundError):
    pass


def discover_patients(training_root: Path) -> list[AcdcPatient]:
    """`training_root` is ACDC's `training/` directory (one subfolder per
    patient, each with an Info.cfg) — see data/README.md for the expected
    layout."""
    training_root = Path(training_root)
    if not training_root.is_dir():
        raise MissingAcdcDataError(
            f"{training_root} does not exist — see data/README.md for where to put ACDC's training/ folder"
        )

    patients = []
    for patient_dir in sorted(training_root.iterdir()):
        if not patient_dir.is_dir():
            continue
        cfg_path = patient_dir / "Info.cfg"
        if not cfg_path.exists():
            continue
        info = _parse_info_cfg(cfg_path)
        patients.append(
            AcdcPatient(
                patient_id=patient_dir.name,
                directory=patient_dir,
                ed_frame=int(info["ED"]),
                es_frame=int(info["ES"]),
                group=info["Group"],
                height_cm=float(info["Height"]) if "Height" in info else None,
                weight_kg=float(info["Weight"]) if "Weight" in info else None,
                nb_frame=int(info.get("NbFrame", 0)),
            )
        )
    if not patients:
        raise MissingAcdcDataError(f"no ACDC patients found under {training_root}")
    return patients
