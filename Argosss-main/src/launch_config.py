"""Utilities for normalizing launch flags for Argos entrypoints."""

from __future__ import annotations

from typing import Iterable, List


def normalize_launch_args(args: Iterable[str]) -> List[str]:
    """Expand convenience flags into explicit launch arguments."""
    normalized = list(args)
    if "--full" not in normalized:
        return normalized

    for required_flag in ("--dashboard", "--wake"):
        if required_flag not in normalized:
            normalized.append(required_flag)
    return normalized
