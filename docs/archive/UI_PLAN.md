# UI Maturity Plan (Historical Through March 15, 2026)

This document tracks the historical UI maturity push that carried the app through the March 15, 2026 submission window. For current and future UI work, use `docs/FUTURE_PLAN.md`.

## Design Principles

- Calm over clever: minimal visual noise, no decorative effects.
- Meaning over decoration: color only when it communicates state/policy.
- Hierarchy first: layout should tell a clear operational story.
- Governance visible: safety and audit signals must be explicit in UI.
- Landing page exception: tasteful entrance animations (fade/slide-in) and count-up counters are allowed on the landing page for first-impression impact. Keep motion subtle and purposeful.

## Current Baseline

- Shadcn-style primitives available:
  - `button`, `card`, `input`, `badge`, `switch`, `table`, `skeleton`, `toast`.
- Migrated surfaces:
  - Dashboard (cards/charts/actions)
  - Activities (filters + table + actions)
  - Settings (controls + explicit-load audit panel).

## Token Baseline (Week 1)

- Surface tiers:
  - `--ph-bg: #091321`
  - `--ph-bg-elevated: #0f1b2f`
  - `--ph-surface: #13233a`
  - `--ph-border: #213651`
- Core text:
  - `--ph-text: #dbe6f4`
  - `--ph-muted: #95a6bc`
- Primary accent:
  - `--ph-accent: #4a86c7`
  - Tailwind `azure` scale updated to a calmer, lower-saturation range (`50`..`900`).
- Card depth:
  - shadow standardized to `0 10px 30px -24px rgba(8, 18, 36, 0.55)`.

## UI Contracts (Week 1)

These are enforceable defaults for all primary product screens.

### Spacing

- Page section gap:
  - default `24px` (`space-y-6`)
  - elevated sections can use `32px` (`space-y-8`) sparingly
- Card padding:
  - mobile `16px` (`p-4`)
  - desktop `20-24px` (`md:p-5` or `md:p-6`)
- Card-to-card gap:
  - default `16px` (`gap-4`)
  - larger groups `24px` (`gap-6`) only for major section boundaries
- Table density:
  - default comfortable mode only in production pages
  - no ad-hoc per-row padding overrides outside shared table primitives.

### Typography

- One page headline style per page (`text-2xl font-bold`).
- Metadata labels use one muted style (`text-sm text-gray-500 dark:text-gray-400`).
- Table content uses one base size (`text-sm`) with `text-xs` only for subordinate metadata.
- Monospace is reserved for IDs/hashes (request IDs, fingerprints).

### Colors

- Blue is reserved for primary actions and active navigation state.
- Green/amber/red are semantic-only: success/warning/blocked.
- No decorative gradients, neon edges, or non-semantic accent colors.
- Border contrast remains subtle and consistent with `--ph-border`.

### Components

- Buttons:
  - use only `default`, `secondary`, `ghost`, `destructive`
  - use consistent sizing per context (`sm` in dense tables, default elsewhere)
- Badges:
  - use semantic variants (`success`, `destructive`) for status
  - use subdued variants (`secondary`, `outline`) for metadata
- Inputs/selects:
  - one consistent control height (`h-10`)
  - one focus-ring behavior (`focus:ring-2 focus:ring-azure-500`)
- Tables:
  - use shared shadcn `Table` primitives only
  - avoid custom `<div>`-based table layouts.

## Week 1 Plan (Completed)

- [x] Establish shared primitives and remove one-off markup for core pages.
- [x] Add skeleton loading states for key dashboard/activity views.
- [x] Add toast feedback for explicit user actions (save/refresh/copy).
- [x] Finalize visual tokens:
  - primary blue (single signature accent)
  - semantic status accents (success/warn/block)
  - background/card/border contrast tiers.
- [x] Formalize component usage rules (when to use `Badge` variants, table density, card spacing).

## Week 1 Checkpoint Log

- [x] Rules written:
  - token baseline
  - spacing/typography/color/component contracts
- [x] Rules applied across:
  - Dashboard
  - Activities
  - Settings
- [x] Screens verified:
  - desktop width
  - mobile width

### Evidence (2026-02-13)

- Verified with Playwright Firefox on local preview (`http://127.0.0.1:4174`).
- Desktop checks:
  - `1280x800`: Dashboard, Activities, Settings
  - `1440x900`: Dashboard, Activities, Settings
- Mobile/tablet checks:
  - `390x844`: Dashboard, Activities, Settings
  - `768x1024`: Dashboard, Activities, Settings
- Validation result:
  - no horizontal overflow (`scrollWidth === innerWidth`) on all verified pages/viewports
  - activities list remains readable in card mode at smaller breakpoints
  - settings audit panel remains readable at mobile and tablet widths

## Week 2 Plan

- [x] Dashboard hierarchy pass:
  - processed -> actioned -> blocked -> reason.
- [x] Outcome area emphasis pass (clarity without color overload).
- [x] Chart legibility pass (labels, contrast, spacing).

### Week 2 Checkpoint (2026-02-13)

- Dashboard above-the-fold now follows story order:
  - Processed -> Actioned -> Safety Gated -> Issue-Only
- Safety framing is explicit:
  - "Why Safety Gated" panel with non-allowlisted/context-aware microcopy
  - reason-code frequency chips sourced from recent activity window
- Explainability is visible without leaving dashboard:
  - selected activity snapshot (failure type, confidence, proposed action, reason code)
  - direct trace link to activity details
- Responsive sanity check (Playwright Firefox, local preview):
  - `1440x900` and `390x844` dashboard overflow check passed (`scrollWidth === innerWidth`)
- Chart readability/empty-state polish:
  - reduced chart visual noise (lighter, horizontal-only gridlines; fewer axis marks)
  - key summary numbers moved into chart card headers
  - consistent chart tooltip copy and compact tooltip styling for mobile
  - empty states standardized with CTA (`Open demo repo`)
  - (Feb 14) axis tick fill changed from `#9ca3af` to `#e2e8f0` for dark-theme contrast; pie chart inline labels added; YAxis width normalized
- Explainability drilldown polish:
  - dashboard snapshot actions now support traceable drilldown (`View activity`, `Open Issue/PR`, `Copy ID`)
  - safety reason codes include short human-readable microcopy
  - snapshot includes compact evidence lines and direct workflow-run link
  - Activities supports `?focus=<activity_id>` with focused badge + timed row highlight + clear-focus control

### Week 2 Evidence

- Screenshots:
  - `docs/screens/week2-dashboard-1440x900.png` (story row + safety framing + explainability actions)
  - `docs/screens/week2-activities-focus-390x844.png` (focused view badge + highlight + clear focus)
- Focused activity used:
  - `84cf0bc9-15e3-49bd-851e-2a24286c64a3`
- Proof links:
  - Example issue: `https://github.com/Canepro/pipelinehealer-demo/issues/60`
  - Example workflow run: `https://github.com/Canepro/pipelinehealer-demo/actions/runs/21976047389`
- Quality gates:
  - `bun run lint` pass
  - `bun run build` pass
  - no horizontal overflow at `1440x900` and `390x844`

## Week 3 Plan

- [x] Settings/audit micro-UX polish:
  - copy feedback consistency
  - empty/error state consistency
  - request ID readability (monospace where appropriate).
- [x] Accessibility pass:
  - keyboard focus visibility
  - contrast checks for badges and table text
  - hit area checks for small icon actions.

### Week 3 Checkpoint (2026-02-13)

- Admin audit trust polish:
  - audit columns standardized to `What Changed`, `Actor`, `Trace`, `When`
  - actor fingerprints and trace IDs rendered in monospace
  - per-row `Copy Trace` action copies request-id + actor + timestamp bundle
  - no-op audit diffs suppressed to reduce scan noise (`old === new` entries hidden)
  - actor display simplified to `Admin (<fingerprint>)` with raw value preserved in tooltip
  - `When` column shows relative + absolute UTC inline
- Edge-state consistency:
  - unified copy for `No activities`, `No safety-gated cases`, `No audit entries yet`
  - empty-state tone and structure aligned across Dashboard, Activities, Settings
- Micro-interaction consistency:
  - secondary/ghost button disabled + hover behavior standardized in shared button variants
- Runtime trust surfaces:
  - added Effective Runtime Policy banner in Settings
  - surfaced `PH_ALLOWED_REPOS` scope and explicit repo list in GitHub Integration
  - mobile nav upgraded to route-safe, notch-safe sheet behavior

### Week 3 Evidence

- Screenshots:
  - `docs/screens/week3-settings-audit-1440x900.png` (audit table labels + monospace trace fields + Copy Trace actions)
  - `docs/screens/week3-settings-audit-390x844.png` (mobile settings with audit section visible)
- Proof references:
  - audit trace IDs used for proof: `week3-proof-audit`, `week3-proof-audit-2`
  - example issue artifact: `https://github.com/Canepro/pipelinehealer-demo/issues/60`
- Quality gates:
  - `bun run lint` pass
  - `bun run build` pass

## Week 4 Plan (Submission Freeze)

- [ ] Freeze non-critical UI changes.
- [ ] Refresh README/UI proof references.
- [ ] Final capture run with `docs/runbooks/DEMO_SCRIPT.md`.
- [ ] Verify API doc (`docs/reference/API.md`) matches runtime contracts.

### Week 4 Checkpoint (2026-02-18)

- Settings information architecture refinement:
  - replaced long single-surface admin controls with section tabs:
    - `Runtime Controls`
    - `AI & Integrations`
    - `Security & Advanced`
  - preserved existing controls/validation; reduced operator scan cost for live demos.
- Activity explainability layering:
  - added `Evidence Layers` block in activity detail:
    - confidence impact per external source
    - structured context extracted from diagnosis payload
    - optional raw log extracts toggle (off by default)
  - keeps default view concise while still enabling trust-building forensic depth.
- MCP observability surfacing:
  - added per-activity `MCP Observability` summary in activity detail (provider, status, read-only, reason).
  - details-on-demand panel now shows:
    - configured MCP tools
    - external source attribution counts
    - tool usage counters (wired for `fetch_failure_context`).
  - GitHub MCP read-only evidence now appears even when `gh-aw` is disabled (decoupled provider path).
- Diagnosis confidence attribution surfacing:
  - added `External Signal Attribution` panel in activity detail:
    - confidence before/after external signal application
    - net external delta
    - per-source rationale chips for confidence adjustments.
- Dashboard ops KPI expansion:
  - added `MCP Runs (30d)` and `LLM Fallback (30d)` chips to the command-center header.

### Week 4 Checkpoint (2026-02-19)

- Control Center readability polish:
  - converted policy/model summary areas from sentence blocks to structured key/value rows
  - improved panel scanability and visual balance without removing governance detail
- Learning queue card density polish:
  - standardized recurring metadata as compact badges (`Runs`, `Success`, `Action`)
  - preserved full candidate detail behind the existing expandable panel
- Settings operator guidance polish:
  - added a concise 4-step workflow card (`Authenticate -> Edit -> Save & Persist -> Verify`)
  - keeps save behavior unchanged while improving first-time operator orientation

## Acceptance Checklist (Per Page)

- [ ] Visual hierarchy is obvious in under 5 seconds.
- [ ] Loading/error/empty states exist and are non-disruptive.
- [ ] Status colors are semantic and consistent.
- [ ] Actions provide immediate feedback (toast, inline state, or badge).
- [ ] No doc mismatch with current runtime behavior.
