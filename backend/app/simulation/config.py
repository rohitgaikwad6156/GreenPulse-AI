"""Central, configurable empirical assumptions for MVP intervention scenarios."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TreeCanopyAssumptions:
    """MVP feature transformations, not measured Pune cooling coefficients.

    Canopy change uses percentage points of one 30 m cell. The initial
    NDVI coefficient is a configurable empirical demonstration assumption
    requiring calibration with local intervention observations.
    """

    cell_area_m2: float = 900.0
    max_canopy_increase_pp: float = 40.0
    ndvi_per_canopy_percentage_point: float = 0.01
    focal_3x3_valid_cells: int = 9
    focal_5x5_valid_cells: int = 25
    ndvi_min: float = -1.0
    ndvi_max: float = 1.0
    assumption_label: str = "CONFIGURABLE EMPIRICAL MVP ASSUMPTION — REQUIRES LOCAL CALIBRATION"
    evidence_status: str = "calibration_required"
    coefficient_source: str = "GreenPulse configurable MVP assumption; no local or authoritative canopy-to-NDVI calibration supplied"
    growth_horizon_source: str = "Qualitative scenario horizon only; no locally validated time-to-canopy model supplied"
    survival_source: str = "Not modelled; no locally validated survival rate supplied"

    def __post_init__(self) -> None:
        numbers = (self.cell_area_m2, self.max_canopy_increase_pp,
                   self.ndvi_per_canopy_percentage_point, self.ndvi_min, self.ndvi_max)
        if (not all(isinstance(value, (int, float)) and math.isfinite(value) for value in numbers)
                or self.cell_area_m2 <= 0 or not 0 < self.max_canopy_increase_pp <= 100
                or self.ndvi_per_canopy_percentage_point < 0
                or self.ndvi_min != -1 or self.ndvi_max != 1
                or not isinstance(self.focal_3x3_valid_cells, int)
                or not 1 <= self.focal_3x3_valid_cells <= 9
                or not isinstance(self.focal_5x5_valid_cells, int)
                or not 1 <= self.focal_5x5_valid_cells <= 25):
            raise ValueError("Invalid tree-canopy MVP assumptions")


def tree_canopy_assumptions_from_env() -> TreeCanopyAssumptions:
    """Load the canopy-to-NDVI coefficient from an optional environment value.

    All other defaults and valid ranges live in this module. Invalid
    environment values fail at startup/use rather than silently resetting.
    """
    raw = os.getenv("GREENPULSE_CANOPY_NDVI_PER_PP")
    if raw is None:
        return TreeCanopyAssumptions()
    try:
        coefficient = float(raw)
    except ValueError as exc:
        raise ValueError("GREENPULSE_CANOPY_NDVI_PER_PP must be numeric") from exc
    return TreeCanopyAssumptions(ndvi_per_canopy_percentage_point=coefficient)


@dataclass(frozen=True)
class CoolRoofAssumptions:
    """Illustrative roof reflectance and optional NDBI surrogate parameters.

    Existing/cool roof albedos are generic MVP assumptions, not measured
    Pune roof properties. k_roof is an empirical calibration coefficient,
    never a physical law. Zero disables NDBI modification by default.
    """

    cell_area_m2: float = 900.0
    max_retrofit_percent_of_eligible_roof: float = 50.0
    existing_roof_albedo: float = 0.20
    cool_roof_albedo: float = 0.65
    k_roof_ndbi_per_retrofit_fraction: float = 0.0
    focal_3x3_valid_cells: int = 9
    focal_5x5_valid_cells: int = 25
    assumption_label: str = "ILLUSTRATIVE COOL-ROOF MVP ASSUMPTIONS — NOT PUNE MEASUREMENTS; CALIBRATION REQUIRED"
    evidence_status: str = "calibration_required"
    albedo_source: str = "Illustrative configurable values; no measured Pune roof-albedo dataset or selected product specification supplied"
    ndbi_source: str = "Disabled by default; no local roof-retrofit-to-NDBI calibration supplied"
    aging_horizon_source: str = "Qualitative comparable-season horizon only; coating aging is not modelled"

    def __post_init__(self) -> None:
        numeric = (self.cell_area_m2, self.max_retrofit_percent_of_eligible_roof,
                   self.existing_roof_albedo, self.cool_roof_albedo,
                   self.k_roof_ndbi_per_retrofit_fraction)
        if (not all(isinstance(value, (int, float)) and math.isfinite(value) for value in numeric)
                or self.cell_area_m2 <= 0
                or not 0 < self.max_retrofit_percent_of_eligible_roof <= 100
                or not 0 <= self.existing_roof_albedo < self.cool_roof_albedo <= 1
                or self.k_roof_ndbi_per_retrofit_fraction < 0
                or not isinstance(self.focal_3x3_valid_cells, int)
                or not 1 <= self.focal_3x3_valid_cells <= 9
                or not isinstance(self.focal_5x5_valid_cells, int)
                or not 1 <= self.focal_5x5_valid_cells <= 25):
            raise ValueError("Invalid cool-roof MVP assumptions")


def cool_roof_assumptions_from_env() -> CoolRoofAssumptions:
    """Read optional roof albedo and k_roof overrides from environment."""
    defaults = CoolRoofAssumptions()

    def configured(name: str, fallback: float) -> float:
        raw = os.getenv(name)
        if raw is None:
            return fallback
        try:
            return float(raw)
        except ValueError as exc:
            raise ValueError(f"{name} must be numeric") from exc

    return CoolRoofAssumptions(
        existing_roof_albedo=configured("GREENPULSE_EXISTING_ROOF_ALBEDO", defaults.existing_roof_albedo),
        cool_roof_albedo=configured("GREENPULSE_COOL_ROOF_ALBEDO", defaults.cool_roof_albedo),
        k_roof_ndbi_per_retrofit_fraction=configured(
            "GREENPULSE_ROOF_NDBI_K", defaults.k_roof_ndbi_per_retrofit_fraction),
    )
