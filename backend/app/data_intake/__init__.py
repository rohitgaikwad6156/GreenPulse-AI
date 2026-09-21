"""Executable provenance contract for GreenPulse real-data inputs."""

from .manifest import ValidationReport, validate_manifest

__all__ = ["ValidationReport", "validate_manifest"]
