"""Validated public request and response contracts for the GreenPulse API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)


class HealthResponse(BaseModel):
    status: Literal["ok"]


class MetricsResponse(BaseModel):
    target: Literal["lst_c"]
    unit: Literal["°C"]
    model_name: str
    dataset_version: str
    spatial_validation_method: str
    metrics: dict[str, Any]


class WardItem(BaseModel):
    ward_id: str
    ward_name: str
    grid_cell_count: int


class WardsResponse(BaseModel):
    wards: list[WardItem]
    total: int
    source: str


class GridCell(BaseModel):
    grid_id: str
    ward_id: str
    ward_name: str
    latitude: float
    longitude: float
    x: float
    y: float
    observed_lst_c: float
    features: dict[str, float]


class GridResponse(BaseModel):
    cells: list[GridCell]
    total: int
    limit: int
    offset: int
    source: str


class WardResponse(BaseModel):
    ward_id: str
    ward_name: str
    grid_cell_count: int
    observed_lst_c_mean: float
    observed_lst_c_min: float
    observed_lst_c_max: float
    unit: Literal["°C"]
    source: str


class GridIdRequest(StrictRequest):
    grid_id: str = Field(min_length=1, max_length=120)


class PredictResponse(BaseModel):
    grid_id: str
    predicted_lst_c: float
    target: Literal["land_surface_temperature"]
    unit: Literal["°C"]
    model_dataset_version: str


class ExplainRequest(GridIdRequest):
    sample_size: int = Field(default=2000, ge=2, le=5000)


class ExplainResponse(BaseModel):
    global_explanation: dict[str, Any]
    local_explanation: dict[str, Any]


class SimulateRequest(GridIdRequest):
    scenario_type: Literal["tree_canopy", "cool_roof", "combined"]
    canopy_increase_percentage_points: float | None = Field(default=None, ge=0, le=40)
    feasible_ground_area_m2: float | None = Field(default=None, ge=0, le=900)
    retrofit_fraction: float | None = Field(default=None, ge=0, le=1)
    eligible_roof_area_m2: float | None = Field(default=None, ge=0, le=900)

    @model_validator(mode="after")
    def validate_scenario(self) -> "SimulateRequest":
        tree = self.scenario_type in {"tree_canopy", "combined"}
        roof = self.scenario_type in {"cool_roof", "combined"}
        if tree and (self.canopy_increase_percentage_points is None
                     or self.feasible_ground_area_m2 is None):
            raise ValueError("Tree scenarios need canopy increase and feasible ground area")
        if roof and (self.retrofit_fraction is None or self.eligible_roof_area_m2 is None):
            raise ValueError("Roof scenarios need retrofit fraction and eligible roof area")
        if not tree and (self.canopy_increase_percentage_points is not None
                         or self.feasible_ground_area_m2 is not None):
            raise ValueError("Tree fields are only valid for tree or combined scenarios")
        if not roof and (self.retrofit_fraction is not None
                         or self.eligible_roof_area_m2 is not None):
            raise ValueError("Roof fields are only valid for roof or combined scenarios")
        if self.scenario_type == "combined" and (
            self.feasible_ground_area_m2 + self.eligible_roof_area_m2 > 900):
            raise ValueError("Ground plus eligible roof area cannot exceed one 900 m² grid cell")
        return self


class SimulateResponse(BaseModel):
    grid_id: str
    scenario_type: str
    baseline_lst_c: float
    scenario_lst_c: float
    delta_lst_c: float
    cooling_magnitude_c: float
    unit: str
    modified_features: dict[str, Any]
    assumptions: dict[str, Any]
    uncertainty: dict[str, Any]
    model_dataset_version: str

    model_config = ConfigDict(extra="allow")


class PriorityWeights(StrictRequest):
    cooling: float = Field(ge=0, le=5)
    green_cover: float = Field(ge=0, le=5)
    co_benefit: float = Field(ge=0, le=5)

    @model_validator(mode="after")
    def at_least_one_priority(self) -> "PriorityWeights":
        if self.cooling + self.green_cover + self.co_benefit <= 0:
            raise ValueError("At least one policy priority must be positive")
        return self


class OptimizeRequest(StrictRequest):
    location: str = Field(min_length=1, max_length=120)
    budget_inr: float = Field(ge=0, le=1_000_000_000_000)
    maintenance_cap_inr_per_year: float = Field(ge=0, le=1_000_000_000_000)
    available_ground_m2: float = Field(ge=0, le=100_000_000)
    available_roof_m2: float = Field(ge=0, le=100_000_000)
    priority_weights: PriorityWeights | None = None


class OptimizeResponse(BaseModel):
    location: str
    status: Literal["optimal"]
    interpretation: str
    selected_actions: list[dict[str, Any]]
    capital_cost_inr: float
    annual_maintenance_inr: float
    ground_used_m2: float
    roof_used_m2: float
    unused_budget_inr: float
    objective_value: float
    modeled_cooling_estimate_c: float
    cooling_estimate_note: str
    normalization: dict[str, Any]
    weights: dict[str, float]
    catalog_label: str


class DidObservation(StrictRequest):
    grid_id: str = Field(min_length=1, max_length=120)
    group: Literal["treated", "control"]
    period: Literal["pre", "post"]
    lst_c: float = Field(ge=-100, le=100)
    ndvi: float | None = Field(default=None, ge=-1, le=1)


class DidPrediction(StrictRequest):
    grid_id: str = Field(min_length=1, max_length=120)
    predicted_delta_lst_c: float = Field(ge=-100, le=100)


class DidRequest(StrictRequest):
    observations: list[DidObservation] = Field(min_length=4)
    intervention: str = Field(min_length=1, max_length=200)
    pre_period: str = Field(min_length=1, max_length=100)
    post_period: str = Field(min_length=1, max_length=100)
    predictions: list[DidPrediction] = Field(default_factory=list)
    scenario_label: Literal["DEMO VALIDATION SCENARIO", "USER-SUPPLIED OBSERVATIONS — PROVENANCE NOT VERIFIED BY API"] = "USER-SUPPLIED OBSERVATIONS — PROVENANCE NOT VERIFIED BY API"
    source_note: str | None = Field(default=None, max_length=500)


class DidResponse(BaseModel):
    label: str
    target: Literal["lst_c"]
    unit: Literal["°C"]
    intervention: str
    pre_period: str
    post_period: str
    group_means_c: dict[str, dict[str, float]]
    counts: dict[str, dict[str, int]]
    treated_change_c: float
    control_change_c: float
    difference_in_differences_c: float
    realized_cooling_c: float
    ndvi_group_means: dict[str, dict[str, float]] | None = None
    ndvi_changes: dict[str, float] | None = None
    prediction_comparison: list[dict[str, Any]]
    performance: dict[str, Any] | None = None
    source_note: str | None = None
    interpretation: str
    limitations: list[str]


class MethodologyResponse(BaseModel):
    system: str
    target: str
    spatial_unit: str
    reporting_unit: str
    pipeline: list[str]
    validation: str
    limitations: list[str]
    data_status: dict[str, bool]
