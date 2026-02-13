# UI Maturity Plan (Through March 15, 2026)

This document tracks visual and UX refinement work for PipelineHealer without changing core remediation logic.

## Design Principles

- Calm over clever: minimal visual noise, no decorative effects.
- Meaning over decoration: color only when it communicates state/policy.
- Hierarchy first: layout should tell a clear operational story.
- Governance visible: safety and audit signals must be explicit in UI.

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

## Week 1 Plan (In Progress)

- [x] Establish shared primitives and remove one-off markup for core pages.
- [x] Add skeleton loading states for key dashboard/activity views.
- [x] Add toast feedback for explicit user actions (save/refresh/copy).
- [x] Finalize visual tokens:
  - primary blue (single signature accent)
  - semantic status accents (success/warn/block)
  - background/card/border contrast tiers.
- [ ] Formalize component usage rules (when to use `Badge` variants, table density, card spacing).

## Week 2 Plan

- [ ] Dashboard hierarchy pass:
  - processed -> actioned -> blocked -> reason.
- [ ] Outcome area emphasis pass (clarity without color overload).
- [ ] Chart legibility pass (labels, contrast, spacing).

## Week 3 Plan

- [ ] Settings/audit micro-UX polish:
  - copy feedback consistency
  - empty/error state consistency
  - request ID readability (monospace where appropriate).
- [ ] Accessibility pass:
  - keyboard focus visibility
  - contrast checks for badges and table text
  - hit area checks for small icon actions.

## Week 4 Plan (Submission Freeze)

- [ ] Freeze non-critical UI changes.
- [ ] Refresh README/UI proof references.
- [ ] Final capture run with `docs/DEMO_SCRIPT.md`.

## Acceptance Checklist (Per Page)

- [ ] Visual hierarchy is obvious in under 5 seconds.
- [ ] Loading/error/empty states exist and are non-disruptive.
- [ ] Status colors are semantic and consistent.
- [ ] Actions provide immediate feedback (toast, inline state, or badge).
- [ ] No doc mismatch with current runtime behavior.
