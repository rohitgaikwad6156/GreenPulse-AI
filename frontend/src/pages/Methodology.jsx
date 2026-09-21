import { useEffect, useState } from "react";
import { ArrowRight, BookOpenText, CircleHelp, FlaskConical, Layers3, ShieldCheck } from "lucide-react";
import PageIntro from "../components/PageIntro.jsx";
import { getMethodology } from "../services/api.js";

const stages = [
  "Satellite + GIS", "30 m grid", "Feature engineering", "XGBoost LST",
  "Spatial validation", "TreeSHAP", "What-if + uncertainty", "MILP action plan", "Follow-up DiD",
];

const sources = [
  {
    name: "Landsat 8/9 Collection 2 Level-2",
    agency: "USGS",
    contribution: "QA-masked ST_B10 provides the observed daytime land surface temperature target, in °C, for March–May composites.",
    detail: "Delivered on a 30 m grid; thermal sensing is coarser. The scale and offset come from each scene's metadata.",
    link: "https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature",
  },
  {
    name: "Sentinel-2 Level-2A",
    agency: "Copernicus",
    contribution: "Cloud-screened B04 red, B08 near-infrared, and B11 shortwave-infrared reflectance produce NDVI and NDBI.",
    detail: "B04/B08 are 10 m; B11 and scene classification are 20 m. Indices are aggregated to the LST-aligned 30 m grid.",
    link: "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html",
  },
  {
    name: "ESA WorldCover 2021 v200",
    agency: "ESA",
    contribution: "Tree-cover and built-up land-cover class fractions form morphology features.",
    detail: "A 10 m classification snapshot from 2021, not a present-day canopy census or a measured roof fraction.",
    link: "https://esa-worldcover.org/en/data-access",
  },
  {
    name: "OpenStreetMap",
    agency: "OSM contributors",
    contribution: "Mapped road lengths, green-space polygons, and optional building footprints support contextual features.",
    detail: "Vector coverage and tagging completeness vary. Ground distances and areas are computed in metric EPSG:32643.",
    link: "https://www.openstreetmap.org/about",
  },
  {
    name: "WorldPop",
    agency: "WorldPop / University of Southampton",
    contribution: "Gridded population estimates supply exposure context for planning and reporting.",
    detail: "Typically around 100 m source detail; unit and year must be checked. A 30 m alignment creates no new people-level detail.",
    link: "https://hub.worldpop.org/project/categories?id=3",
  },
];

const equations = [
  {
    name: "NDVI · vegetation",
    formula: "NDVI = (B08 − B04) / (B08 + B04 + ε)",
    explanation: "Sentinel-2 near-infrared and red surface reflectance; ε = 10⁻⁸ protects the denominator. Unitless, approximately −1 to 1.",
  },
  {
    name: "NDBI · built-surface spectral contrast",
    formula: "NDBI = (B11 − B08) / (B11 + B08 + ε)",
    explanation: "Sentinel-2 shortwave-infrared and near-infrared reflectance; B11 starts at 20 m. It is not a measured impervious-area fraction.",
  },
  {
    name: "LST · physical target",
    formula: "T_K = M_T × DN + A_T    ;    LST_C = T_K − 273.15",
    explanation: "Convert Landsat Level-2 stored ST_B10 using that scene's metadata scale M_T and offset A_T. Mask invalid QA pixels first. LST is surface temperature.",
  },
  {
    name: "MAE · typical absolute error",
    formula: "MAE = (1/n) Σ |yᵢ − ŷᵢ|",
    explanation: "Mean absolute difference between observed and predicted LST on held-out cells, in °C. Smaller is better.",
  },
  {
    name: "RMSE · larger misses weigh more",
    formula: "RMSE = √[(1/n) Σ (yᵢ − ŷᵢ)²]",
    explanation: "Root mean squared held-out error, in °C. Squaring gives larger errors more influence than MAE.",
  },
  {
    name: "R² · held-out variation explained",
    formula: "R² = 1 − [Σ (yᵢ − ŷᵢ)² / Σ (yᵢ − ȳ)²]",
    explanation: "Use the held-out fold's observed mean ȳ. R² can be negative; it is undefined if the denominator is zero.",
  },
  {
    name: "TreeSHAP · model explanation",
    formula: "f(x) = E[f(X)] + Σⱼ φⱼ",
    explanation: "A baseline model output plus feature contributions φⱼ reconstructs a cell's predicted LST. Contributions are in °C, not causal effects.",
  },
  {
    name: "Scenario · re-predict changed inputs",
    formula: "ΔLST = f_XGB(x_scenario) − f_XGB(x_base)    ;    Cooling = max(0, −ΔLST)",
    explanation: "Tree canopy or eligible cool-roof assumptions change model inputs, then XGBoost runs again. A negative ΔLST is modeled cooling, not an observed outcome.",
  },
  {
    name: "Uncertainty · approximate MVP range",
    formula: "σ_param = |Ĉ| × CV    ;    σ_total = √(RMSE_spatial² + σ_param²)",
    explanation: "Approximate 90% cooling range: [max(0, Ĉ − 1.645σ_total), Ĉ + 1.645σ_total]. The nominal coverage is not calibrated; CV assumptions are configurable.",
  },
  {
    name: "MILP · normalized objective",
    formula: "uᵢ = α(Cᵢ/C_ref) + β(Gᵢ/G_ref) + γ(Bᵢ/10)    ;    maximize Σᵢ uᵢxᵢ",
    explanation: "C is modeled per-block cooling, G is green gain, B is a co-benefit score. References normalize units; xᵢ is an integer block count. SciPy minimizes −u.",
  },
  {
    name: "MILP · hard limits",
    formula: "Σ costᵢxᵢ ≤ Budget  ;  Σ upkeepᵢxᵢ ≤ Maintenance  ;  Σ groundᵢxᵢ ≤ A_ground  ;  Σ roofᵢxᵢ ≤ A_roof  ;  0 ≤ xᵢ ≤ Uᵢ, integer",
    explanation: "Uᵢ is a verified site capacity. The result is optimal only for the supplied linear objective, candidate blocks, and constraints.",
  },
  {
    name: "Difference-in-Differences · follow-up",
    formula: "DiD = (T_treated,post − T_treated,pre) − (T_control,post − T_control,pre)",
    explanation: "Imported validation uses complete treated/control grid panels, multiple pre-periods, scene/season/QA provenance, control and spillover diagnostics, and limited sample uncertainty. A DiD value or passed pre-trend diagnostic is not causal proof.",
  },
];

const limitations = [
  ["LST ≠ 2 m air temperature", "The target is daytime surface skin temperature. Pedestrian heat exposure needs separate, well-placed air and comfort observations."],
  ["Clear-sky satellite sampling", "Cloud masking leaves a selected set of visible surfaces and overpass times; a seasonal composite is not a continuous daily temperature record."],
  ["Landsat temporal frequency", "Each Landsat 8/9 satellite repeats in roughly 16 days; together they are offset by about 8 days before cloud losses."],
  ["Cloud and monsoon gaps", "Cloud/shadow and seasonal gaps can remove cells or dates. No-data remains missing, never zero or an invented reading."],
  ["2D grid approximation", "The 30 m squares do not resolve 3D street canyons, moving shade, wind, or adjacent-cell spillover. Native thermal sensing is coarser than the grid."],
  ["Tree growth latency", "A canopy slider represents an assumed future feature state. Saplings need time, space, water, and survival; immediate mature-canopy cooling is not established."],
  ["Intervention coefficient uncertainty", "NDVI-per-canopy and roof-albedo response are configurable MVP assumptions needing local calibration. The nominal uncertainty range has untested coverage."],
  ["Sparse ground sensors", "Ground stations may be too sparse or mismatched in height and time to validate every cell. No citywide air-temperature truth is inferred."],
  ["Research physics and automation", "CFD, 3D canyon physics, tree-species growth/survival, continuous IoT ingestion, and automatic retraining remain future scope."],
  ["SHAP attribution ≠ causation", "SHAP divides a model prediction. Correlated NDVI/canopy and NDBI/built features can shift individual attributions without changing physical mechanisms."],
  ["MILP optimality depends on assumptions", "Integer optimality applies only to candidate benefits, costs, capacity, weights, and linear constraints entered. The summed cooling is a planning proxy."],
];

const questions = [
  ["Why predict LST instead of a 0–100 score?", "LST in °C is an observable continuous target. The Heat Hazard Score is a separate display transformation after prediction, not an ML training label."],
  ["Why spatial blocks instead of a random split?", "Nearby cells share surface patterns and even thermal source pixels. Five held-out folds of about 5 km blocks test transfer to distinct places more honestly; tuning stays inside training folds."],
  ["Do the sliders predict guaranteed cooling?", "No. The what-if engine changes features using documented assumptions and re-runs the fitted model. Its cooling and range are sensitivity estimates until calibrated against intervention follow-up."],
  ["Is the action plan the best real-world plan?", "Only under the modeled objective, evidence-complete integer actions, verified location capacities, budget, maintenance, and space constraints. The demo CSV is not used; locations remain unavailable until every evidence gate passes."],
  ["How do you check results after installation?", "Import checksum-verified treated/control grid panels with at least two pre periods, matching season/overpass/QA provenance, then review parallel trends, spillover, spatial autocorrelation, uncertainty, and residuals. Calibration proposals require a separate human approval record."],
];

const references = [
  ["GreenPulse AI research document", "Primary project reference; local PDF, particularly the data, modeling, optimization, and validation sections."],
  ["USGS Landsat Surface Temperature", "https://www.usgs.gov/landsat-missions/landsat-collection-2-surface-temperature"],
  ["USGS Landsat quality bands", "https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands"],
  ["Copernicus Sentinel-2 L2A bands", "https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/S2L2A.html"],
  ["ESA WorldCover data", "https://esa-worldcover.org/en/data-access"],
  ["OpenStreetMap", "https://www.openstreetmap.org/about"],
  ["WorldPop population counts", "https://hub.worldpop.org/project/categories?id=3"],
  ["XGBoost regressor", "https://xgboost.readthedocs.io/en/latest/python/python_api.html"],
  ["TreeSHAP documentation", "https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html"],
  ["SciPy MILP", "https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html"],
  ["scikit-learn GroupKFold", "https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html"],
];

function Heading({ id, eyebrow, title, description }) {
  return <div id={id} className="scroll-mt-24">
    <p className="text-[11px] font-bold uppercase tracking-[0.16em] text-[#4a8559]">{eyebrow}</p>
    <h2 className="mt-1 text-xl font-semibold tracking-tight text-[#264533]">{title}</h2>
    {description && <p className="mt-2 max-w-3xl text-sm leading-6 text-[#6e8072]">{description}</p>}
  </div>;
}

function EquationCard({ item }) {
  return <article className="min-w-0 rounded-xl border border-[#e1eae0] bg-white p-4 sm:p-5">
    <h3 className="text-sm font-semibold text-[#294532]">{item.name}</h3>
    <div className="mt-3 overflow-x-auto rounded-lg bg-[#f3f7f2] px-3 py-3 font-mono text-xs leading-6 text-[#315a3b]">
      <span className="whitespace-nowrap">{item.formula}</span>
    </div>
    <p className="mt-3 text-xs leading-5 text-[#6d7e70]">{item.explanation}</p>
  </article>;
}

export default function Methodology() {
  const [status, setStatus] = useState({ loading: true, data: null, error: "" });
  useEffect(() => {
    const controller = new AbortController();
    getMethodology(controller.signal)
      .then((data) => setStatus({ loading: false, data, error: "" }))
      .catch((error) => {
        if (error.name !== "CanceledError") setStatus({ loading: false, data: null, error: "Live artifact status is unavailable. Check the backend connection." });
      });
    return () => controller.abort();
  }, []);

  const files = status.data?.data_status;
  return <>
    <PageIntro eyebrow="Research foundation" title="Methodology & Limitations"
      description="The data, equations, validation rules, and scientific boundaries behind GreenPulse AI — An AI-powered Urban Climate Decision-Support System." />

    <section className="rounded-2xl border border-[#dbe8dc] bg-[#f1f7f0] p-5 sm:p-6">
      <div className="flex items-center gap-2 text-[#397a50]"><ShieldCheck size={20} aria-hidden="true" /><h2 className="text-sm font-semibold text-[#294532]">What can be claimed today?</h2></div>
      <p className="mt-2 max-w-4xl text-sm leading-6 text-[#536d59]">The processing, model-training, simulation, optimization, and validation methods are implemented. A real Pune/PCMC result requires verified boundary and satellite inputs, a trained model, calibrated intervention benefits, and follow-up observations. DEMO / SYNTHETIC DATA is never reported as measured climate evidence.</p>
      {status.loading ? <p role="status" className="mt-3 text-xs text-[#69806d]">Checking local artifact availability…</p>
        : status.error ? <p role="status" className="mt-3 text-xs text-[#8d683a]">{status.error}</p>
          : <div className="mt-4 flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-[#cddfcf] bg-white px-3 py-1.5 text-[#31543b]">Real ML grid: {files.real_ml_grid_available ? "file present" : "not available"}</span>
            <span className="rounded-full border border-[#cddfcf] bg-white px-3 py-1.5 text-[#31543b]">Trained model: {files.trained_model_available ? "file present" : "not available"}</span>
            <span className="rounded-full border border-[#cddfcf] bg-white px-3 py-1.5 text-[#31543b]">Planning catalog: {!files.intervention_catalog_available ? "not available" : files.optimizer_location_available ? "evidence-complete location available" : "loaded; no evidence-complete locations"}</span>
          </div>}
    </section>

    <nav aria-label="Methodology sections" className="mt-5 flex flex-wrap gap-2">
      {[["#data", "Data"], ["#mathematics", "Mathematics"], ["#model", "Model"], ["#validation", "Validation"],
        ["#limitations", "Limitations"], ["#judge-questions", "Judge questions"], ["#references", "References"]]
        .map(([href, label]) => <a key={href} href={href} className="rounded-lg border border-[#dce7dc] bg-white px-3 py-2 text-xs font-semibold text-[#3e6e4c] hover:bg-[#edf5ec]">{label}</a>)}
    </nav>

    <section className="mt-7 rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
      <div className="flex items-center gap-2 text-[#397a50]"><Layers3 size={18} aria-hidden="true" /><h2 className="text-sm font-semibold text-[#294532]">End-to-end research pipeline</h2></div>
      <ol className="mt-4 flex flex-wrap items-center gap-2">
        {stages.map((stage, index) => <li key={stage} className="flex items-center gap-2">
          <span className="rounded-lg bg-[#f0f6ef] px-3 py-2 text-xs font-medium text-[#355c40]">{index + 1}. {stage}</span>
          {index < stages.length - 1 && <ArrowRight size={14} className="text-[#8aa592]" aria-hidden="true" />}
        </li>)}
      </ol>
      <p className="mt-4 text-xs leading-5 text-[#718276]">Prediction target: continuous LST in °C. Analysis unit: 30 m × 30 m cell in EPSG:32643. Reporting unit: verified PMC/PCMC ward. The 30 m grid does not increase the source thermal resolution.</p>
    </section>

    <section className="mt-10">
      <Heading id="data" eyebrow="01 / Data" title="Where each input comes from"
        description="The first model uses a March–May peak-summer composite. Source year, QA, grid alignment, and missingness must be recorded for every actual acquisition." />
      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {sources.map((source) => <article key={source.name} className="rounded-2xl border border-[#e4ebe3] bg-white p-5">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[#5b9270]">{source.agency}</p>
          <h3 className="mt-1 text-sm font-semibold text-[#294532]">{source.name}</h3>
          <p className="mt-3 text-xs leading-5 text-[#617566]">{source.contribution}</p>
          <p className="mt-2 text-xs leading-5 text-[#819084]">{source.detail}</p>
          <a href={source.link} target="_blank" rel="noreferrer" className="mt-3 inline-block text-xs font-semibold text-[#397a50] underline underline-offset-2">Official source ↗</a>
        </article>)}
      </div>
      <p className="mt-4 rounded-xl border border-[#e4ebe3] bg-[#f8faf7] p-4 text-xs leading-5 text-[#6b7e6e]">Ward boundaries require a verified PMC/PCMC version. Optional air temperature, humidity, or AQI stations are separate measurements and do not turn satellite LST into 2 m air temperature.</p>
    </section>

    <section className="mt-10">
      <Heading id="mathematics" eyebrow="02 / Mathematics" title="Equations used in the system"
        description="The equations are shown with their units and their role. None of the symbols below implies a measured Pune result by itself." />
      <div className="mt-5 grid gap-3 lg:grid-cols-2">{equations.map((item) => <EquationCard key={item.name} item={item} />)}</div>
    </section>

    <section className="mt-10 grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
        <Heading id="model" eyebrow="03 / Model" title="XGBoost regression" />
        <p className="mt-4 text-sm leading-6 text-[#617566]">The main estimator sums regularized regression trees to predict continuous grid-cell LST: ŷ = Σₖ fₖ(x). The configured objective is <span className="font-mono text-[#315a3b]">reg:squarederror</span>. Candidate features include NDVI, NDBI, tree-cover and built fractions, albedo when sourced, road context, distance to green space, and focal optical means.</p>
        <p className="mt-3 text-xs leading-5 text-[#718276]">Linear regression, decision tree, and random forest provide baseline comparisons on the same spatial folds. Coordinates and ward IDs are metadata for this MVP, not default model inputs. Model metrics are unavailable without a real trained artifact.</p>
      </div>
      <div className="rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
        <Heading id="validation" eyebrow="04 / Validation" title="Spatial holdout and follow-up" />
        <p className="mt-4 text-sm leading-6 text-[#617566]">Projected cells are assigned to approximately 5 km × 5 km blocks. Five folds hold out complete blocks; no block appears in both training and validation for a fold. Hyperparameter tuning uses spatial folds, not a random cell split.</p>
        <p className="mt-3 text-xs leading-5 text-[#718276]">After installation, compare paired treated and control cells, calculate descriptive DiD and ΔNDVI, then compare each treated cell's control-adjusted observed change with its predicted ΔLST. Nearby cells still share source pixels; block edges and seasonal confounding need review.</p>
      </div>
    </section>

    <section className="mt-10">
      <Heading id="limitations" eyebrow="05 / Limits" title="What this prototype cannot establish"
        description="These are practical checks to raise in a technical review, not footnotes to hide from decision makers." />
      <ol className="mt-5 grid gap-3 md:grid-cols-2">
        {limitations.map(([title, detail], index) => <li key={title} className="flex gap-3 rounded-xl border border-[#e4ebe3] bg-white p-4">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-[#edf5ec] text-xs font-bold text-[#397a50]">{index + 1}</span>
          <div><h3 className="text-sm font-semibold text-[#294532]">{title}</h3><p className="mt-1 text-xs leading-5 text-[#718276]">{detail}</p></div>
        </li>)}
      </ol>
    </section>

    <section className="mt-10 rounded-2xl border border-[#dce9dd] bg-[#f0f6ef] p-5 sm:p-6">
      <div className="flex items-center gap-2 text-[#397a50]"><CircleHelp size={19} aria-hidden="true" /><h2 id="judge-questions" className="scroll-mt-24 text-lg font-semibold text-[#294532]">Questions judges may ask</h2></div>
      <div className="mt-4 grid gap-3 lg:grid-cols-2">
        {questions.map(([question, answer]) => <article key={question} className="rounded-xl border border-[#dce9dd] bg-white p-4">
          <h3 className="text-sm font-semibold text-[#294532]">{question}</h3><p className="mt-2 text-xs leading-5 text-[#617566]">{answer}</p>
        </article>)}
      </div>
    </section>

    <section id="references" className="mt-10 scroll-mt-24 rounded-2xl border border-[#e4ebe3] bg-white p-5 sm:p-6">
      <div className="flex items-center gap-2 text-[#397a50]"><BookOpenText size={19} aria-hidden="true" /><h2 className="text-sm font-semibold text-[#294532]">Research and technical sources</h2></div>
      <ul className="mt-4 grid gap-2 sm:grid-cols-2">
        {references.map(([label, value]) => <li key={label} className="text-xs leading-5 text-[#617566]">
          {value.startsWith("https://") ? <a href={value} target="_blank" rel="noreferrer" className="font-medium text-[#397a50] underline underline-offset-2">{label} ↗</a>
            : <><span className="font-semibold text-[#294532]">{label}:</span> {value}</>}
        </li>)}
      </ul>
      <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-[#718276]"><FlaskConical size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> Any synthetic validation scenario is DEMO DATA. It must not be cited as observed Pune climate evidence or as measured model performance.</p>
    </section>
  </>;
}
