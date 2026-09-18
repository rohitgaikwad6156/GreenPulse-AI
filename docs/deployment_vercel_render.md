# Deploy GreenPulse AI: Render API + Vercel dashboard

This is a deployment checklist for the current repository. The API can deploy
before any real satellite/ML artifacts exist. It will return explicit
unavailable responses for features that require those artifacts.

Repository: https://github.com/rohitgaikwad6156/GreenPulse-AI

## 1. Deploy FastAPI on Render first

1. Sign in to https://dashboard.render.com and connect your GitHub account.
2. Select **New > Web Service** and choose `rohitgaikwad6156/GreenPulse-AI`.
3. Enter these settings:

   | Render field | GreenPulse value |
   | --- | --- |
   | Name | `greenpulse-api` (or another available name) |
   | Branch | `main` |
   | Language | Python 3 |
   | Root Directory | Leave blank: repository root |
   | Build Command | `pip install -r backend/requirements-shap.txt -r backend/requirements-optimizer.txt` |
   | Start Command | `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT` |
   | Health Check Path | `/api/health` |
   | Instance type | Free for an initial attempt; monitor memory |

   Keep Root Directory blank. Setting it to `backend` hides sibling `data/`
   and breaks the current `backend.app` imports. The SHAP requirements include
   the nested data, ML, and XGBoost requirements. The optimizer requirements
   add SciPy explicitly. Do not use only `backend/requirements.txt` for this
   application because map and model modules are imported at startup.

4. Create the service. Render uses its current Python default unless you set
   a version. The project was tested locally with Python 3.14; if selecting a
   different version, check the pinned package wheels first.
5. Wait for the service to become **Live**, then copy its exact public HTTPS
   base URL, such as `https://greenpulse-api.onrender.com`. The actual URL is
   assigned by Render; do not use this example unless it is your URL.
6. Open `<YOUR_RENDER_URL>/api/health`. Expected response:
   `{"status":"ok"}`. Open `<YOUR_RENDER_URL>/docs` for Swagger.

The Render free web service currently has 512 MB RAM and sleeps after 15
minutes without inbound traffic. The first request after sleep can be slow.
The geospatial, XGBoost, and SHAP imports are substantial: if startup logs
show out-of-memory, choose a plan with enough RAM or reduce startup imports
before using it for a public demonstration. Render's free filesystem is
ephemeral; don't rely on runtime-generated rasters, models, or SHAP files
surviving restart. No real model, raster, or ward boundary is in GitHub now.

## 2. Deploy React/Vite on Vercel

1. Sign in to https://vercel.com/new and import the same GitHub repository.
2. In **Configure Project**, select `frontend` as **Root Directory**.
3. Confirm these build settings:

   | Vercel field | GreenPulse value |
   | --- | --- |
   | Framework Preset | Vite |
   | Install Command | `npm ci` (or Vercel's npm default) |
   | Build Command | `npm run build` |
   | Output Directory | `dist` |

4. Before clicking **Deploy**, add the Production environment variable:

   `VITE_API_BASE_URL=<YOUR_RENDER_HTTPS_BASE_URL>`

   Use the bare origin with `https://`, no `/api`, no `/docs`, and no trailing
   slash. This variable is embedded at Vite build time, so redeploy after
   changing it. Never use `localhost` or `127.0.0.1` for a cloud deployment.
5. Deploy and copy the resulting exact `https://...vercel.app` production URL.
6. `frontend/vercel.json` rewrites deep links to `index.html` so refreshing
   `/heat-map`, `/scenario-simulator`, or `/methodology` loads React Router.

## 3. Connect browser access with CORS

1. Return to the Render web service > **Environment**.
2. Set `GREENPULSE_CORS_ORIGINS` to the exact Vercel production origin, for
   example `https://your-actual-project.vercel.app`. Do not include a path or
   trailing slash. Render must restart/redeploy to read the new setting.
3. For multiple known origins, use comma separation, for example:
   `https://your-project.vercel.app,https://your-custom-domain.example`.
   Preview deployments receive changing URLs; register a known preview origin
   before using one. Do not use `*` as a shortcut for this public app.
4. Reopen the Vercel site. The Overview health card should say
   **Backend Status: Healthy** after the Render service wakes.

## 4. Verify and understand the current data gate

- Open the Vercel home page, then refresh `/heat-map` and `/methodology`
  directly. They should load as React pages, not return a Vercel 404.
- In the browser's Network tab, verify the health request goes to the Render
  HTTPS origin and returns 200. The backend `/docs` page should list APIs.
- Methodology should report that the real ML grid and trained model are not
  available. Map/prediction/simulation/optimization features must report
  unavailable rather than show fabricated Pune climate results.
- The bundled validation example is **DEMO / SYNTHETIC DATA**. It can test the
  interface, but it is not post-implementation evidence.

## Common deployment failures

| Symptom | Check |
| --- | --- |
| Render `ModuleNotFoundError` | Root Directory is blank; build installed both requirements files; start command uses `backend.app.main:app`. |
| Render port error | Start command binds `0.0.0.0` and `$PORT`. |
| Render out of memory | Inspect logs and choose adequate RAM or slim imports. |
| Vercel build fails | Root Directory is `frontend`; Vite build is `npm run build`; output is `dist`. |
| Refreshing a dashboard route gives 404 | Confirm `frontend/vercel.json` is in the deployed commit. |
| Frontend calls local machine | Set Production `VITE_API_BASE_URL` to the real Render HTTPS origin and redeploy. |
| Browser CORS error | Render `GREENPULSE_CORS_ORIGINS` exactly matches the browser origin, with no path or trailing slash. |
| Health request initially slow | A free Render service may be waking from idle. |
| Climate route returns 503 | Required verified real-data/model artifacts are absent; deploy alone does not generate them. |
