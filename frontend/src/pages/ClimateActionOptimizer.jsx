import { useEffect, useMemo, useRef, useState } from "react";
import { AlertCircle, BarChart3, Leaf, SlidersHorizontal, Wallet } from "lucide-react";
import { CartesianGrid, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import PageIntro from "../components/PageIntro.jsx";
import { getOptimizerConfig, getOptimizerLocations, optimizePortfolio } from "../services/api.js";
import { buildOptimizerPayload } from "../utils/optimizerPlanning.js";

const integer = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const decimal = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });
const money = (value) => `₹${integer.format(value)}`;
const area = (value) => `${decimal.format(value)} m²`;
const cooling = (value) => `${decimal.format(value)} °C`;

function ConstraintRow({ label, used, limit, formatter }) {
  const percentage = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  return <div className="space-y-1.5">
    <div className="flex justify-between gap-3 text-xs text-[#617566]">
      <span>{label}</span><span className="text-right font-semibold text-[#294532]">{formatter(used)} / {formatter(limit)}</span>
    </div>
    <div className="h-2 rounded-full bg-[#e7eee6]" role="meter" aria-label={`${label} used`}
      aria-valuemin={0} aria-valuemax={Math.max(1, limit)} aria-valuenow={used}>
      <div className="h-2 rounded-full bg-[#4d9061]" style={{ width: `${percentage}%` }} />
    </div>
  </div>;
}

function PrioritySlider({ label, value, onChange }) {
  return <div>
    <div className="flex justify-between text-xs font-medium text-[#294532]">
      <label htmlFor={`priority-${label}`}>{label}</label><span>{value.toFixed(1)}</span>
    </div>
    <input id={`priority-${label}`} type="range" min="0" max="5" step="0.1" value={value}
      onChange={(event) => onChange(Number(event.target.value))} className="mt-2 w-full accent-[#397a50]" />
  </div>;
}

function ChartTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return <div className="rounded-xl border border-[#dfe8de] bg-white p-3 text-xs shadow-lg">
    <p className="font-semibold text-[#294532]">{point.name}</p>
    <p className="mt-1">Capital: {money(point.cost)}</p>
    <p>Modeled cooling proxy: {cooling(point.cooling)}</p>
  </div>;
}

export default function ClimateActionOptimizer() {
  const [location, setLocation] = useState("");
  const [locationCatalog, setLocationCatalog] = useState(null);
  const [budget, setBudget] = useState("");
  const [maintenance, setMaintenance] = useState("");
  const [weights, setWeights] = useState(null);
  const [configError, setConfigError] = useState("");
  const [runEnabled, setRunEnabled] = useState(false);
  const [runTick, setRunTick] = useState(0);
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [plan, setPlan] = useState(null);
  const [previousPlan, setPreviousPlan] = useState(null);
  const latestPlan = useRef(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([getOptimizerConfig(controller.signal), getOptimizerLocations(controller.signal)])
      .then(([config, locations]) => {
        setWeights(config.weights);
        setLocationCatalog(locations);
        if (locations.locations.length === 1) setLocation(locations.locations[0].location_id);
      })
      .catch((requestError) => {
        if (requestError.name !== "CanceledError") setConfigError("Optimizer settings are unavailable. Check the backend connection.");
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!runEnabled || !weights) return undefined;
    let payload;
    try {
      payload = buildOptimizerPayload({
        locationId: location.trim(), budget, maintenance, weights,
        loadedLocations: locationCatalog?.locations,
      });
    } catch (validationError) {
      setStatus("error"); setError(validationError.message); setPlan(null);
      return undefined;
    }
    const controller = new AbortController();
    setStatus("loading"); setError(""); setPlan(null);
    const timer = window.setTimeout(async () => {
      try {
        const result = await optimizePortfolio(payload, controller.signal);
        if (controller.signal.aborted) return;
        setPreviousPlan(latestPlan.current);
        latestPlan.current = result;
        setPlan(result);
        setStatus("success");
      } catch (requestError) {
        if (controller.signal.aborted || requestError.name === "CanceledError") return;
        latestPlan.current = null;
        setPreviousPlan(null);
        setStatus("error");
        if (requestError.response?.status === 503) {
          const detail = requestError.response.data?.detail;
          setError(`No defensible portfolio is available yet. ${typeof detail === "string" ? detail : "Required catalog evidence is unavailable."} No actions or chart values have been fabricated.`);
        } else if (requestError.response?.status === 422) {
          const detail = requestError.response.data?.detail;
          setError(typeof detail === "string" ? detail : "Check the planning inputs and catalog location.");
        } else {
          setError(requestError.message || "The optimizer could not be reached.");
        }
      }
    }, 400);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [runEnabled, runTick, location, locationCatalog, budget, maintenance, weights]);

  const selectedLocation = locationCatalog?.locations.find((item) => item.location_id === location);

  const sliderMax = Math.max(10_000_000, Math.ceil((Number(budget) || 0) / 1_000_000) * 1_000_000);
  const greenGain = plan?.selected_actions.reduce((sum, action) => sum + action.green_cover_gain_m2, 0) ?? 0;
  const chartActions = useMemo(() => plan?.selected_actions.map((action) => ({
    name: action.name, cost: action.capital_cost_inr, cooling: action.modeled_cooling_proxy_c,
  })) ?? [], [plan]);
  const chartPortfolio = plan ? [{ name: "Current portfolio", cost: plan.capital_cost_inr,
    cooling: plan.modeled_cooling_estimate_c }] : [];
  const chartPrevious = previousPlan ? [{ name: "Previous portfolio", cost: previousPlan.capital_cost_inr,
    cooling: previousPlan.modeled_cooling_estimate_c }] : [];
  const previousQuantities = Object.fromEntries(previousPlan?.selected_actions.map((action) => [action.intervention_id, action.quantity]) ?? []);
  const currentQuantities = Object.fromEntries(plan?.selected_actions.map((action) => [action.intervention_id, action.quantity]) ?? []);
  const changedActions = [...new Set([...Object.keys(previousQuantities), ...Object.keys(currentQuantities)])]
    .filter((id) => (previousQuantities[id] || 0) !== (currentQuantities[id] || 0)).length;

  return <>
    <PageIntro eyebrow="Budgeted decisions" title="Climate Action Optimizer"
      description="Allocate discrete intervention blocks under capital, maintenance, ground, roof, and site-capacity limits." />
    <div className="grid gap-5 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
      <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 shadow-[0_2px_14px_rgba(27,58,39,0.035)] sm:p-6">
        <div className="flex items-center gap-2 text-[#397a50]"><SlidersHorizontal size={19} aria-hidden="true" />
          <h2 className="text-sm font-semibold text-[#294532]">Planning constraints</h2></div>
        <p className="mt-2 text-xs leading-5 text-[#718276]">Use verified limits for one ward or planning area. Amounts are Indian rupees; ₹10 lakh = ₹1,000,000.</p>
        <form className="mt-6 space-y-5" onSubmit={(event) => { event.preventDefault(); setRunEnabled(true); setRunTick((tick) => tick + 1); }}>
          <label className="block text-sm font-medium text-[#294532]">Verified ward or planning area
            <select value={location} onChange={(event) => setLocation(event.target.value)}
              disabled={!locationCatalog?.locations.length}
              className="mt-2 w-full rounded-xl border border-[#dce7dc] bg-white px-3 py-2.5 text-sm outline-none focus:border-[#5a9a6c] disabled:cursor-not-allowed disabled:bg-[#f3f5f2]">
              <option value="">{locationCatalog?.locations.length ? "Select a loaded location" : "No evidence-complete locations loaded"}</option>
              {locationCatalog?.locations.map((item) => <option key={item.location_id} value={item.location_id}>
                {item.name} ({item.location_id})
              </option>)}
            </select>
          </label>
          {selectedLocation && <div className="rounded-xl bg-[#f5f9f4] p-3 text-xs leading-5 text-[#617566]">
            <p className="font-semibold text-[#294532]">Verified spatial capacities</p>
            <p>Ground {area(selectedLocation.eligible_ground_m2)} · Roof {area(selectedLocation.eligible_roof_m2)} · {selectedLocation.available_interventions} supported interventions</p>
            <p>CRS {selectedLocation.crs}; {selectedLocation.capacity_status.replaceAll("_", " ")}</p>
          </div>}
          <div>
            <label htmlFor="capital-budget" className="block text-sm font-medium text-[#294532]">Capital budget (INR)</label>
            <input id="capital-budget" type="number" min="0" max="1000000000000" step="1000" value={budget}
              onChange={(event) => setBudget(event.target.value)} placeholder="Enter a verified budget"
              className="mt-2 w-full rounded-xl border border-[#dce7dc] px-3 py-2.5 text-sm outline-none focus:border-[#5a9a6c]" />
            <input type="range" aria-label="Capital budget slider" min="0" max={sliderMax} step="50000"
              value={Math.min(Number(budget) || 0, sliderMax)} onChange={(event) => setBudget(event.target.value)}
              className="mt-4 w-full accent-[#397a50]" />
            <div className="flex justify-between text-[11px] text-[#7b8c7e]"><span>₹0</span><span>{money(sliderMax)}</span></div>
            <p className="mt-2 text-xs text-[#617566]">Moving the slider reruns the solver after a plan has been requested.</p>
          </div>
          <label className="block text-sm font-medium text-[#294532]">Annual maintenance limit (INR/year)
            <input type="number" min="0" max="1000000000000" step="1000" value={maintenance}
              onChange={(event) => setMaintenance(event.target.value)} placeholder="Verified annual limit"
              className="mt-2 w-full rounded-xl border border-[#dce7dc] px-3 py-2.5 text-sm outline-none focus:border-[#5a9a6c]" />
          </label>
          <div className="border-t border-[#e8eee7] pt-5">
            <h3 className="text-sm font-semibold text-[#294532]">Policy priorities</h3>
            <p className="mt-1 text-xs leading-5 text-[#718276]">These weights rank normalized benefits. They do not change intervention science or make cooling causal.</p>
            {weights ? <div className="mt-4 space-y-4">
              <PrioritySlider label="Cooling" value={weights.cooling} onChange={(value) => setWeights({ ...weights, cooling: value })} />
              <PrioritySlider label="Greening" value={weights.green_cover} onChange={(value) => setWeights({ ...weights, green_cover: value })} />
              <PrioritySlider label="Co-benefits" value={weights.co_benefit} onChange={(value) => setWeights({ ...weights, co_benefit: value })} />
            </div> : <p className="mt-3 text-xs text-[#718276]">Loading objective settings…</p>}
          </div>
          <button type="submit" disabled={!weights || !location || status === "loading"}
            className="w-full rounded-xl bg-[#397a50] px-5 py-2.5 text-sm font-semibold text-white hover:bg-[#2d6842] disabled:cursor-not-allowed disabled:opacity-50">
            {status === "loading" ? "Solving portfolio…" : "Optimize action portfolio"}
          </button>
        </form>
        {configError && <p role="alert" className="mt-4 text-sm text-[#94652e]">{configError}</p>}
        {locationCatalog?.total === 0 && <div role="status" className="mt-4 rounded-xl border border-[#eadfca] bg-[#fcf8f0] p-4 text-xs leading-5 text-[#856834]">
          <p className="font-semibold">Planning is evidence-gated</p>
          {locationCatalog.blockers.map((blocker) => <p key={blocker} className="mt-1">{blocker}</p>)}
        </div>}
      </section>

      <div className="space-y-5">
        {status === "idle" && <section className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-center">
          <Wallet className="mx-auto text-[#79a984]" size={30} aria-hidden="true" />
          <h2 className="mt-4 text-base font-semibold text-[#294532]">No portfolio requested</h2>
          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-[#718276]">Select a loaded location and enter verified financial limits. Recommendations appear only when the catalog passes cost, capacity, model, version, checksum, and provenance gates.</p>
        </section>}
        {status === "loading" && <section role="status" className="rounded-2xl border border-[#e4ebe3] bg-white p-8 text-sm text-[#617566]">Updating the integer action portfolio for these constraints…</section>}
        {status === "error" && <section role="alert" className="flex gap-3 rounded-2xl border border-[#eadfca] bg-[#fcf8f0] p-5 text-sm leading-6 text-[#856834]">
          <AlertCircle size={19} className="mt-0.5 shrink-0" aria-hidden="true" /><p>{error}</p>
        </section>}
        {status === "success" && plan && <>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <div className="flex items-start justify-between gap-3">
              <div><p className="text-xs font-bold uppercase tracking-[0.12em] text-[#5c8465]">{plan.location_name} · {plan.location}</p>
                <h2 className="mt-1 text-lg font-semibold text-[#294532]">Recommended Climate Action Portfolio</h2></div>
              <Leaf size={23} className="text-[#397a50]" aria-hidden="true" />
            </div>
            <p className="mt-2 text-xs leading-5 text-[#718276]">{plan.interpretation} {plan.catalog_label}</p>
            {previousPlan && <p className="mt-3 rounded-lg bg-[#f3f8f2] px-3 py-2 text-xs text-[#31543b]">
              Budget {money(previousPlan.capital_cost_inr + previousPlan.unused_budget_inr)} → {money(Number(budget))}; {changedActions} intervention quantities changed.
            </p>}
            {plan.selected_actions.length === 0 ? <p className="mt-5 text-sm text-[#718276]">No intervention blocks fit the current modeled constraints.</p>
              : <div className="mt-5 grid gap-3">
                {plan.selected_actions.map((action) => <article key={action.intervention_id} className="rounded-xl border border-[#e4ebe3] bg-[#fbfcfa] p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h3 className="text-sm font-semibold text-[#294532]">{action.name}</h3>
                    <span className="text-sm font-semibold text-[#397a50]">{action.quantity} × {decimal.format(action.block_size)} {action.unit_type}</span>
                  </div>
                  <dl className="mt-3 grid gap-x-4 gap-y-3 text-xs sm:grid-cols-2">
                    <div><dt className="text-[#7b8c7e]">Area used</dt><dd className="mt-0.5 font-medium text-[#294532]">Ground {area(action.ground_used_m2)} · Roof {area(action.roof_used_m2)}</dd></div>
                    <div><dt className="text-[#7b8c7e]">Capital cost</dt><dd className="mt-0.5 font-medium text-[#294532]">{money(action.capital_cost_inr)}</dd></div>
                    <div><dt className="text-[#7b8c7e]">Annual maintenance</dt><dd className="mt-0.5 font-medium text-[#294532]">{money(action.annual_maintenance_inr)}/year</dd></div>
                    <div><dt className="text-[#7b8c7e]">Modeled cooling proxy</dt><dd className="mt-0.5 font-medium text-[#294532]">{cooling(action.modeled_cooling_proxy_c)}</dd></div>
                    <div><dt className="text-[#7b8c7e]">Green cover gain</dt><dd className="mt-0.5 font-medium text-[#294532]">{area(action.green_cover_gain_m2)}</dd></div>
                    <div><dt className="text-[#7b8c7e]">Time horizon</dt><dd className="mt-0.5 font-medium text-[#294532]">{action.time_horizon || "Not supplied in catalog"}</dd></div>
                    <div><dt className="text-[#7b8c7e]">Evidence</dt><dd className="mt-0.5 font-medium text-[#294532]">{action.evidence_status} · {action.source_ids.join(", ")}</dd></div>
                    <div><dt className="text-[#7b8c7e]">Uncertainty</dt><dd className="mt-0.5 font-medium text-[#294532]">{action.uncertainty?.status?.replaceAll("_", " ") || "Not supplied"}</dd></div>
                  </dl>
                </article>)}
              </div>}
          </section>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <div className="flex items-center gap-2 text-[#397a50]"><Wallet size={18} aria-hidden="true" /><h2 className="text-sm font-semibold text-[#294532]">Portfolio summary</h2></div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[["Total budget", money(Number(budget))], ["Used budget", money(plan.capital_cost_inr)],
                ["Remaining budget", money(plan.unused_budget_inr)], ["Estimated cooling proxy", cooling(plan.modeled_cooling_estimate_c)],
                ["Roof used", area(plan.roof_used_m2)], ["Ground used", area(plan.ground_used_m2)],
                ["Green gain", area(greenGain)], ["Annual maintenance", `${money(plan.annual_maintenance_inr)}/year`]]
                .map(([label, value]) => <div key={label} className="rounded-xl bg-[#f7faf6] p-3"><p className="text-xs text-[#718276]">{label}</p><p className="mt-1 text-base font-semibold text-[#294532]">{value}</p></div>)}
            </div>
            <h3 className="mt-6 text-sm font-semibold text-[#294532]">Constraints used</h3>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <ConstraintRow label="Capital" used={plan.capital_cost_inr} limit={Number(budget)} formatter={money} />
              <ConstraintRow label="Annual maintenance" used={plan.annual_maintenance_inr} limit={Number(maintenance)} formatter={money} />
              <ConstraintRow label="Ground" used={plan.ground_used_m2} limit={plan.verified_capacity.eligible_ground_m2} formatter={area} />
              <ConstraintRow label="Roof" used={plan.roof_used_m2} limit={plan.verified_capacity.eligible_roof_m2} formatter={area} />
            </div>
            <p className="mt-4 text-xs leading-5 text-[#718276]">Each quantity is an integer and also respects its catalog maximum feasible units. Active normalized weights: cooling {plan.weights.cooling}, greening {plan.weights.green_cover}, co-benefits {plan.weights.co_benefit}.</p>
          </section>
          <section className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
            <div className="flex items-center gap-2 text-[#397a50]"><BarChart3 size={18} aria-hidden="true" /><h2 className="text-sm font-semibold text-[#294532]">Cost vs modeled cooling</h2></div>
            <p className="mt-2 text-xs leading-5 text-[#718276]">Each green point is a selected intervention total. Orange is the current portfolio; gray is the prior portfolio when a budget or constraint changes.</p>
            {chartActions.length ? <div className="mt-4 h-[290px] w-full" role="img" aria-label="Scatter chart of selected intervention capital cost against modeled cooling proxy">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 12, right: 20, bottom: 18, left: 16 }}>
                  <CartesianGrid stroke="#e8eee7" strokeDasharray="3 3" />
                  <XAxis type="number" dataKey="cost" name="Capital cost" tickFormatter={(value) => `₹${integer.format(value)}`}
                    tick={{ fontSize: 11, fill: "#718276" }} label={{ value: "Capital cost (INR)", position: "insideBottom", offset: -12, fontSize: 11 }} />
                  <YAxis type="number" dataKey="cooling" name="Modeled cooling proxy" unit=" °C"
                    tick={{ fontSize: 11, fill: "#718276" }} width={62} />
                  <Tooltip content={<ChartTip />} />
                  <Scatter name="Selected interventions" data={chartActions} fill="#4d9061" />
                  <Scatter name="Previous portfolio" data={chartPrevious} fill="#9aa9a0" />
                  <Scatter name="Current portfolio" data={chartPortfolio} fill="#d3834f" />
                </ScatterChart>
              </ResponsiveContainer>
            </div> : <p className="mt-5 text-xs text-[#718276]">No selected actions to chart at this budget.</p>}
            <p className="mt-3 text-xs leading-5 text-[#718276]">{plan.cooling_estimate_note}</p>
            <p className="mt-2 text-xs font-medium leading-5 text-[#94652e]">{plan.interaction_warning}</p>
          </section>
        </>}
        <section className="rounded-2xl border border-[#dce9dd] bg-[#edf5ec] p-5 text-xs leading-5 text-[#607d66]">
          <h2 className="text-sm font-semibold text-[#294532]">Evidence and scope</h2>
          <p className="mt-2">The demo CSV is not connected to this screen. Only versioned locations with verified spatial capacity, traceable costs and maintenance, supported benefits, source-file checksums, and current model provenance can appear in the selector.</p>
          <p className="mt-2">A solved plan is optimal under the modeled objective, assumptions and constraints. Summed marginal LST cooling is a planning proxy, not a ward-average LST forecast or pedestrian air temperature benefit.</p>
        </section>
      </div>
    </div>
  </>;
}
