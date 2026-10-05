# Workspace visual design review

## Scope

Reviewed the existing overview, map, analysis, simulator, optimizer, validation,
research-layer and methodology routes before updating the shared interface.
The changes concern presentation and navigation. Existing API requests, source
selection, map layers, scientific calculations and evidence requirements remain
unchanged.

## Findings and decisions

- The overview gave four similar status cards priority over the next action.
  It now opens with a clear map action and a secondary methodology link, followed
  by one research-readiness panel. Connected services and missing research inputs
  are visibly different states.
- Eight equally weighted navigation links made the research sequence harder to
  scan. The forest-green rail groups them into Explore, Plan & evaluate, and
  Reference, while preserving every route and label.
- Repeated outlined cards made the workflow feel fragmented. Stages now form a
  single ordered list with concise descriptions and persistent requirements.
- A warm paper background, restrained green palette, readable headings, shared
  action styles and quieter separators provide hierarchy without decorative
  gradients or glass effects. The interpretation note remains beside the workflow
  on wide screens and follows it on smaller screens.
- The mobile drawer previously lacked dialog semantics and keyboard management.
  It now uses a modal dialog, explicit forward/reverse focus wrapping, Escape
  dismissal, scroll locking and focus restoration. Route changes reset scroll,
  focus the main content and update the document title. A skip link is available.
- The map's long inline selects are now a responsive grid. Source choices have
  larger clickable labels and a visible selected state. Mobile text inputs use
  16 px text to avoid automatic input zoom; controls retain their existing values
  and handlers.
- Route loading uses a shared live status and restrained placeholders. Motion
  respects reduced-motion preferences. Existing missing-data messages remain
  available; connection failures do not masquerade as missing research inputs.

## Verification

Run locally with Vite and the existing FastAPI service:

- `npm --prefix frontend run build`: passed.
- `npm --prefix frontend test`: 17 tests passed.
- All eight routes inspected in Chromium at 1440 x 1000 and 320 x 800:
  correct headings, no page-wide horizontal overflow and no Vite error overlay.
- Overview and simulator screenshots reviewed at 390 x 844 and desktop size;
  map controls additionally reviewed at 320 px in research-model mode.
- Both map source choices remained available. Model layer, spatial-view and
  season selects fit within the narrow viewport.
- Mobile menu tested with Tab, Shift+Tab and Escape. Focus wraps inside the menu;
  Escape returns focus to its trigger. Selecting a route closes the drawer,
  unlocks scrolling and focuses main content.
- Backend requests temporarily blocked in the browser: service connection error
  and `Not checked` displayed. Restoring requests and using Refresh status
  returned `Connected` with the real input availability state.
- Reduced-motion media preference checked. No uncaught browser errors observed.
- `git diff --check`: passed.

These are local browser checks, not a full accessibility certification. Actual
model predictions and populated analytical charts cannot be verified against
production evidence while the required real grid and trained model are absent.
No demonstration results were introduced to fill that gap. Live satellite tile
coverage remains dependent on the external imagery service.

## Repeating the visual checks

1. Start the backend and frontend using the repository's normal development setup.
2. Visit each route at desktop, 390 px and 320 px viewport widths.
3. Follow Overview > Heat Map, switch source controls, and inspect the planning
   forms and their unavailable-data guidance.
4. Open the mobile menu, cycle forward and backward through its links, dismiss
   with Escape, and follow a link to confirm focus and scroll behavior.
5. Block the API in browser developer tools, refresh readiness, then restore it
   and retry. A failed request must remain distinct from absent inputs.

## Route error recovery

Each of the nine page routes, including Overview, renders inside a reusable error
boundary within `AppShell`. A render or lifecycle exception replaces only the
page content with a calm recovery card; the sidebar, header, and footer remain
available. The boundary sits outside each route's existing `Suspense` fallback.
It does not handle event-handler exceptions or asynchronous request failures.

Retry resets the boundary and remounts the failed page subtree. For recognized
lazy-chunk import failures, Retry reloads the document once on user action so a
stale deployment can fetch fresh assets. A route change gives the destination a
new boundary, so an error on one page cannot follow the user to another. The
fallback uses a heading and alert semantics, moves focus to that heading on a
crash, and offers a button plus a normal router link back to Overview. AppShell
continues to manage focus when the route itself changes.

Expected evidence and API states, including unavailable models, missing source
data, and service errors, keep their existing page-specific messages. They are
not converted into generic render errors.

### Recovery verification

- All nine normal routes and the unknown-path redirect were checked in Chromium.
- A temporary development render throw in Heat Map and Overview showed the
  recovery card without removing AppShell. The heading received focus and no
  error message or stack appeared in the card. The temporary throws were removed.
- Clearing the throw and choosing Retry restored Heat Map. With the throw still
  active, navigation to Data Readiness and Return to Overview both cleared the
  route error. Overview's own Return to Overview action also recovered after
  the throw was cleared.
- A temporarily blocked lazy module showed the recovery card; after unblocking,
  Retry loaded the page. A delayed lazy import showed the existing PageLoading
  status before the page rendered. The network block and delay were removed.
- The fallback was visually inspected at 1440, 390, and 320 px; the narrow
  layouts had no horizontal overflow. Ordinary unavailable API states continued
  to display within their pages.
