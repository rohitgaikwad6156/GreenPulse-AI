from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import APP_NAME, CORS_ORIGINS
from .api.routes import router as greenpulse_router
from .api.map_routes import router as map_router
from .schemas.api import HealthResponse
from .simulation.config import cool_roof_assumptions_from_env, tree_canopy_assumptions_from_env


app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(greenpulse_router)
app.include_router(map_router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "GreenPulse AI backend is running"}


@app.get("/api/health", response_model=HealthResponse)
def health_check() -> dict[str, str]:
    return {"status": "ok"}


class TreeCanopyRequest(BaseModel):
    grid_id: str = Field(min_length=1)
    canopy_increase_percentage_points: float
    feasible_ground_area_m2: float | None = None


class CoolRoofRequest(BaseModel):
    grid_id: str = Field(min_length=1)
    retrofit_percent_of_eligible_roof: float
    eligible_roof_area_m2: float | None = None


class CombinedScenarioRequest(TreeCanopyRequest, CoolRoofRequest):
    pass


class ClimatePlanRequest(BaseModel):
    location: str = Field(min_length=1)
    budget_inr: float = Field(ge=0)
    maintenance_cap_inr_per_year: float = Field(ge=0)
    available_ground_m2: float = Field(ge=0)
    available_roof_m2: float = Field(ge=0)


@app.post("/api/optimizer/plan")
def climate_action_plan(request: ClimatePlanRequest) -> dict:
    """Optimize discrete actions after location-specific benefits/capacities exist."""
    from .optimizer.milp_optimizer import OptimizerDataUnavailableError, optimize_catalog

    catalog = Path(__file__).resolve().parents[2] / "data" / "processed" / "interventions.csv"
    try:
        return optimize_catalog(catalog, **request.model_dump())
    except OptimizerDataUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _scenario_paths() -> tuple[Path, Path, Path]:
    root = Path(__file__).resolve().parents[2]
    return (root / "data" / "processed" / "greenpulse_ml_grid.parquet",
            root / "models" / "xgboost_lst.joblib",
            root / "models" / "model_metadata.json")


@app.get("/api/simulation/tree-canopy/config")
def tree_canopy_config() -> dict:
    """Expose the configured slider bounds and clearly labelled MVP assumption."""
    try:
        settings = tree_canopy_assumptions_from_env()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "max_canopy_increase_percentage_points": settings.max_canopy_increase_pp,
        "cell_area_m2": settings.cell_area_m2,
        "ndvi_per_canopy_percentage_point": settings.ndvi_per_canopy_percentage_point,
        "assumption_label": settings.assumption_label,
        "evidence_status": settings.evidence_status,
        "provenance": {"canopy_to_ndvi": settings.coefficient_source,
                       "growth_horizon": settings.growth_horizon_source,
                       "survival": settings.survival_source},
    }


@app.post("/api/simulation/tree-canopy")
def tree_canopy_scenario(request: TreeCanopyRequest) -> dict:
    """Re-predict a selected real grid cell with changed canopy features."""
    from .ml.uncertainty import UncertaintyUnavailableError, add_uncertainty_to_scenario
    from .simulation.tree_canopy import SimulationUnavailableError, simulate_saved_grid_cell

    try:
        paths = _scenario_paths()
        scenario = simulate_saved_grid_cell(
            *paths,
            request.grid_id,
            request.canopy_increase_percentage_points,
            request.feasible_ground_area_m2,
        )
        return add_uncertainty_to_scenario(scenario, paths[2], ("tree_canopy",))
    except UncertaintyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SimulationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/simulation/cool-roof/config")
def cool_roof_config() -> dict:
    """Expose roof slider limits and illustrative albedo/NDBI assumptions."""
    try:
        settings = cool_roof_assumptions_from_env()
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        "max_retrofit_percent_of_eligible_roof": settings.max_retrofit_percent_of_eligible_roof,
        "cell_area_m2": settings.cell_area_m2,
        "existing_roof_albedo": settings.existing_roof_albedo,
        "cool_roof_albedo": settings.cool_roof_albedo,
        "k_roof_ndbi_per_retrofit_fraction": settings.k_roof_ndbi_per_retrofit_fraction,
        "assumption_label": settings.assumption_label,
        "evidence_status": settings.evidence_status,
        "provenance": {"roof_albedo": settings.albedo_source,
                       "roof_to_ndbi": settings.ndbi_source,
                       "aging_horizon": settings.aging_horizon_source},
    }


@app.post("/api/simulation/cool-roof")
def cool_roof_scenario(request: CoolRoofRequest) -> dict:
    """Re-predict LST after area-weighted roof albedo modification."""
    from .ml.uncertainty import UncertaintyUnavailableError, add_uncertainty_to_scenario
    from .simulation.cool_roof import simulate_saved_cool_roof
    from .simulation.tree_canopy import SimulationUnavailableError

    try:
        paths = _scenario_paths()
        scenario = simulate_saved_cool_roof(
            *paths, request.grid_id,
            request.retrofit_percent_of_eligible_roof,
            request.eligible_roof_area_m2)
        return add_uncertainty_to_scenario(scenario, paths[2], ("cool_roof",))
    except UncertaintyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SimulationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/simulation/combined")
def combined_scenario(request: CombinedScenarioRequest) -> dict:
    """Apply both interventions and predict their joint model response."""
    from .ml.uncertainty import UncertaintyUnavailableError, add_uncertainty_to_scenario
    from .simulation.cool_roof import simulate_saved_combined
    from .simulation.tree_canopy import SimulationUnavailableError

    try:
        paths = _scenario_paths()
        scenario = simulate_saved_combined(
            *paths, request.grid_id,
            request.canopy_increase_percentage_points,
            request.feasible_ground_area_m2,
            request.retrofit_percent_of_eligible_roof,
            request.eligible_roof_area_m2)
        return add_uncertainty_to_scenario(scenario, paths[2], ("tree_canopy", "cool_roof"))
    except UncertaintyUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SimulationUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
