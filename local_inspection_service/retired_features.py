"""Retired feature policy for the modular monolith.

This module owns Phase 1 removal semantics so endpoint stubs and public
sanitizers do not grow independent copies of the same retired-field policy.
"""

from __future__ import annotations

from fastapi import HTTPException


REMOVED_PHASE1_PUBLIC_CONFIG_KEYS = frozenset(
    {
        "locateanything_profile",
        "locateanything_profile_status",
        "locateanything_profile_ready",
    }
)


def removed_phase1_feature(feature: str) -> None:
    raise HTTPException(status_code=410, detail=f"{feature} has been removed from the Phase 1 core product.")
