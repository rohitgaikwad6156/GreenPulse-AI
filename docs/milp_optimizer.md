# Location-specific climate action optimizer

The optimizer reads [`data/interventions/location_catalog.json`](../data/interventions/location_catalog.json), not the demo CSV. The committed catalog is schema version `1.0` and currently contains no enabled planning location because the repository does not contain the complete real evidence needed for one. This is an intentional evidence gate, not a demo fallback.

## Location catalog contract

The machine-readable schema is [`schemas/location_intervention_catalog.schema.json`](../schemas/location_intervention_catalog.schema.json). A location must name its planning-area ID and name, use `EPSG:32643`, identify verified capacity sources, and store eligible ground and roof area calculated from spatial inputs. Each available action must include:

- positive block size and integer capital/annual-maintenance INR;
- ground and roof use per block and an integer maximum feasible unit count;
- modeled marginal LST cooling per block, green-cover gain, 0–5 co-benefit score, horizon, and uncertainty status/description;
- `verified` or `audited` evidence status and source IDs;
- matching location ID, model dataset version, and model artifact SHA-256 where tree/cool-roof benefits use the model workflow.

Sources record organization, title, URL or identifier, license, access date, required validity end date, evidence type, local evidence path, and SHA-256. Each action maps every evidence-bearing field to source IDs. Runtime validation checks each local file and rejects expired, tampered, missing, mixed-location, duplicated, over-capacity, or model-mismatched evidence. Cost evidence must be a municipal tender, schedule of rates, published study, or audited user input. Capacity must cite verified spatial evidence. Cooling must cite a validated model or published study. Unsupported actions use `availability: "unavailable"` with a reason and do not enter the solver.

Tree-canopy and cool-roof rows may use the validated scenario pipeline only when the real grid/model are present, model and dataset hashes match, the scenario stays within training support, selected cells belong to the same location, intervention amount maps exactly to the catalog block, and the aggregation method/horizon is documented in a hashed evidence artifact. A single-cell scenario is not silently generalized to a ward. The current missing real artifacts therefore block generation of those rows.

## Commands and API

```powershell
.\.venv\Scripts\python.exe scripts\validate_intervention_catalog.py
.\.venv\Scripts\python.exe -m unittest tests.test_location_intervention_catalog tests.test_milp_optimizer -v
```

Validation returns exit code `0` only when at least one location is evidence-complete, `3` when the catalog is structurally valid but has no enabled location, and `2` for invalid evidence.

`GET /api/optimizer/locations` returns only evidence-complete selectable locations and verified capacities. `POST /api/optimize` accepts `location_id`, capital budget, annual maintenance cap, and optional objective weights. Ground/roof limits come from the catalog and cannot be overridden by the caller.

The MILP preserves integer quantities plus capital, annual maintenance, ground, roof, and per-intervention maximum-unit constraints. Its cooling total is the sum of marginal effects as a linear planning proxy. Physical overlap, interactions, competition for space, aging, and spillover are not jointly simulated; the API and UI always return this warning. “Optimal” means optimal only under the catalog evidence, objective, and constraints—not a causal or observed cooling guarantee.
