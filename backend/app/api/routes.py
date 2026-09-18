"""Frontend-facing API routes for observed grids, saved ML, and planning."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.app.api import services
from backend.app.schemas.api import (
    DidRequest, DidResponse, ExplainRequest, ExplainResponse, GridIdRequest,
    GridResponse, MethodologyResponse, MetricsResponse, OptimizeRequest,
    OptimizeResponse, PredictResponse, SimulateRequest, SimulateResponse,
    WardResponse, WardsResponse,
)


router = APIRouter(prefix="/api", tags=["GreenPulse MVP"])


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


@router.get("/model/metrics", response_model=MetricsResponse)
def get_model_metrics() -> dict:
    """Return saved held-out spatial CV metrics, never illustrative numbers."""
    try:
        return services.model_metrics()
    except services.DataUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.get("/wards", response_model=WardsResponse)
def get_wards() -> dict:
    """List ward identifiers and cell counts from the real 30 m table."""
    try:
        return services.list_wards()
    except services.DataUnavailableError as exc:
        raise _unavailable(exc) from exc


@router.get("/grid", response_model=GridResponse)
def get_grid(limit: int = Query(default=100, ge=1, le=500),
             offset: int = Query(default=0, ge=0),
             ward_id: str | None = Query(default=None, min_length=1, max_length=120)) -> dict:
    """Page real grid cells; observed LST is clearly separate from prediction."""
    try:
        return services.list_grid(limit=limit, offset=offset, ward_id=ward_id)
    except services.DataUnavailableError as exc:
        raise _unavailable(exc) from exc
    except services.ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/ward/{ward_id}", response_model=WardResponse)
def get_ward(ward_id: str) -> dict:
    """Summarize observed LST cells in one documented ward."""
    if not ward_id.strip() or len(ward_id) > 120:
        raise HTTPException(status_code=422, detail="ward_id must be 1–120 nonblank characters")
    try:
        return services.ward_summary(ward_id)
    except services.DataUnavailableError as exc:
        raise _unavailable(exc) from exc
    except services.ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/predict", response_model=PredictResponse)
def post_predict(request: GridIdRequest) -> dict:
    """Predict physical LST °C for one real cell with the matching saved model."""
    try:
        return services.predict_grid_cell(request.grid_id)
    except services.DataUnavailableError as exc:
        raise _unavailable(exc) from exc
    except services.ResourceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/explain", response_model=ExplainResponse)
def post_explain(request: ExplainRequest) -> dict:
    """Return global and local TreeSHAP reports in model-output °C."""
    if not all(path.is_file() for path in (services.GRID, services.GRID_METADATA,
                                           services.MODEL, services.MODEL_METADATA)):
        raise HTTPException(status_code=503, detail="Real ML grid and matching trained model are required")
    from backend.app.ml.shap_explain import explain_saved_model
    try:
        global_report, local_report = explain_saved_model(
            services.GRID, services.MODEL, services.MODEL_METADATA,
            request.grid_id, services.ROOT / "data" / "processed" / "shap",
            request.sample_size)
        return {"global_explanation": global_report, "local_explanation": local_report}
    except ValueError as exc:
        if "grid_id was not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=503, detail=f"Model explanation unavailable: {exc}") from exc


@router.post("/simulate", response_model=SimulateResponse)
def post_simulate(request: SimulateRequest) -> dict:
    """Run one XGBoost input-change scenario and attach approximate uncertainty."""
    from backend.app.ml.uncertainty import UncertaintyUnavailableError, add_uncertainty_to_scenario
    from backend.app.simulation.cool_roof import simulate_saved_combined, simulate_saved_cool_roof
    from backend.app.simulation.tree_canopy import SimulationUnavailableError, simulate_saved_grid_cell
    paths = (services.GRID, services.MODEL, services.MODEL_METADATA)
    try:
        if request.scenario_type == "tree_canopy":
            result = simulate_saved_grid_cell(
                *paths, request.grid_id, request.canopy_increase_percentage_points,
                request.feasible_ground_area_m2)
            types = ("tree_canopy",)
        elif request.scenario_type == "cool_roof":
            result = simulate_saved_cool_roof(
                *paths, request.grid_id, request.retrofit_fraction * 100,
                request.eligible_roof_area_m2)
            types = ("cool_roof",)
        else:
            result = simulate_saved_combined(
                *paths, request.grid_id, request.canopy_increase_percentage_points,
                request.feasible_ground_area_m2, request.retrofit_fraction * 100,
                request.eligible_roof_area_m2)
            types = ("tree_canopy", "cool_roof")
        result["scenario_type"] = request.scenario_type
        return add_uncertainty_to_scenario(result, services.MODEL_METADATA, types)
    except (SimulationUnavailableError, UncertaintyUnavailableError) as exc:
        raise _unavailable(exc) from exc
    except ValueError as exc:
        if "grid_id was not found" in str(exc):
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if "metadata" in str(exc).lower() or "model" in str(exc).lower():
            raise _unavailable(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/optimize", response_model=OptimizeResponse)
def post_optimize(request: OptimizeRequest) -> dict:
    """Solve an integer-block plan only with completed location-specific inputs."""
    from backend.app.optimizer.milp_optimizer import OptimizerDataUnavailableError, optimize_catalog
    try:
        return optimize_catalog(services.CATALOG, **request.model_dump())
    except OptimizerDataUnavailableError as exc:
        raise _unavailable(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise _unavailable(exc) from exc


@router.get("/optimizer/config", tags=["Climate action optimizer"])
def get_optimizer_config() -> dict:
    """Read the active objective weights and normalization assumptions."""
    from backend.app.optimizer.milp_optimizer import load_objective_config
    try:
        return load_objective_config()
    except ValueError as exc:
        raise _unavailable(exc) from exc


@router.post("/validation/did", response_model=DidResponse)
def post_validation_did(request: DidRequest) -> dict:
    """Calculate descriptive DID from caller-supplied paired observed LST."""
    from backend.app.validation.did import calculate_did
    try:
        return calculate_did(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/validation/demo", response_model=DidRequest)
def get_validation_demo() -> dict:
    """Return only a clearly labelled DEMO / SYNTHETIC validation scenario."""
    from backend.app.validation.did import load_demo_scenario
    try:
        return load_demo_scenario()
    except (OSError, ValueError) as exc:
        raise _unavailable(exc) from exc


@router.get("/methodology", response_model=MethodologyResponse)
def get_methodology() -> dict:
    """Describe the system and actual local artifact availability."""
    return services.methodology()
