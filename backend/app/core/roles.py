"""Canonical role names, matching docs/permissions.md exactly.

This is the single source of truth for valid role strings — the seed script,
the Role table rows, and every `require_roles(...)` check reference this enum
rather than hardcoding string literals that could drift out of sync.
"""
from enum import Enum


class RoleName(str, Enum):
    ADMIN = "ADMIN"
    DOCTOR = "DOCTOR"
    ANNOTATOR = "ANNOTATOR"
    ML_ENGINEER = "ML_ENGINEER"
    MODEL_APPROVER = "MODEL_APPROVER"
    AUDITOR = "AUDITOR"
