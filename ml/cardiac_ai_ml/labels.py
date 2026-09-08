"""Segmentation mask label convention.

Matches the ACDC (Automated Cardiac Diagnosis Challenge) convention, the most
common ground-truth format for cardiac cine-MRI segmentation datasets, so
masks from public datasets can be used as synthetic/ground-truth fixtures
without remapping.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class CardiacLabels:
    background: int = 0
    right_ventricle_cavity: int = 1
    myocardium: int = 2
    left_ventricle_cavity: int = 3


DEFAULT_LABELS = CardiacLabels()
