# Design: GL.iNet API browser (GitHub Pages)

- **Date:** 2026-06-27
- **Status:** Approved (design); pending implementation plan
- **Consumes:** the enumerator's captured reports (`docs/devices/<id>.json`, produced by `gli4py-enumerate`).
- **Goal:** A static GitHub Pages site that renders the captured API surface as a **per-model browser** — pick a model+firmware, see its services→methods with status/risk/coverage, and filter within.

## 1. Scope

In scope:
- A **local build step** that projects raw reports into a **sanitized, published dataset** (model + firmware + per-method API shape; no device identifiers, no values).
- A **static site** (vanilla HTML/JS/CSS) that loads the dataset and renders a per-model API browser with search + filter toggles.
- A **GitHub Actions Pages** deploy workflow.
- Committed **sample data** (the sanitized `mt6000_4.9.0` projection) so the site has real content.

Out of scope: a cross-model comparison matrix (deferred follow-up); building the dataset in CI (the maintainer builds locally and commits sanitized output — raw reports are never committed); any framework/bundler; auth.

## 2. Data flow

```
docs/devices/<id>.json            raw reports (mac/sn/sn_bak + values) — NOT committed
        │  scripts/build_site_data.py   (sanitizing projection; run locally)
        ▼
site/data/index.json              manifest [{id, model, firmware_version, counts}]   ┐ committed,
site/data/devices/<id>.json       sanitized per-device API surface                   ┘ public
        │  static fetch()
        ▼
site/index.html + app.js + style.css   →  GitHub Pages (Actions deploy of site/)
```

The build script is the **only** code that reads raw reports; it strips identifiers and values so nothing identifying is ever published. Raw `docs/devices/*.json` stay local and uncommitted.

## 3. Build script — `scripts/build_site_data.py`

CLI: `python scripts/build_site_data.py [--reports docs/devices] [--out site/data]` (also runnable via `uv run`). Reads every `*.json` in `--reports`, projects each, and writes `site/data/index.json` + `site/data/devices/<id>.json`.

Two pure, unit-tested functions:

- **`project_report(raw: dict) -> dict`** — the sanitizing projection:
  - `device`: keep ONLY an allowlist — `model`, `firmware_version`, `vendor`, `device_type`, `hardware_version`. **Drop everything else** (notably `mac`, `sn`, `sn_bak`, `ddns`, `country_code`, `hidden_features`, `software_feature`, `hardware_feature`).
  - `services`: for each `service → method`, keep `{status, error_code, risk, discovered_by, covered_by, params, schema}` and **drop `value`** entirely.
  - Add `id` (the report's device id, from `model_firmware` slug — reuse `gli4py.enumerator.probe.device_id`).
- **`build_manifest(devices: list[dict]) -> dict`** — `{ "devices": [ {id, model, firmware_version, service_count, available_count, not_wrapped_count} ] }`, where:
  - `available_count` = methods with `status` in `{available, needs_params}` (the "present" set, matching the report renderer).
  - `service_count` = services with ≥1 present method.
  - `not_wrapped_count` = present methods with `covered_by is None`.

If `--reports` has no JSON files, write an empty manifest (`{"devices": []}`) and no device files — the site handles the empty case.

## 4. Published per-device schema (`site/data/devices/<id>.json`)

```json
{
  "id": "mt6000_4.9.0",
  "model": "mt6000",
  "firmware_version": "4.9.0",
  "vendor": "GL.iNet",
  "device_type": "...",
  "hardware_version": "...",
  "services": {
    "system": {
      "get_info": {
        "status": "available", "error_code": null, "risk": "read",
        "discovered_by": "catalog", "covered_by": "router_info",
        "params": null, "schema": {"model": "str", "firmware_version": "str", "...": "..."}
      }
    }
  }
}
```

No `mac`/`sn`/`sn_bak`, no method `value`s.

## 5. The site (vanilla, no build tooling)

Three files under `site/`:

- **`index.html`** — header/title; a **model select** (`<select id="device">`); a filter bar (`<input id="search">`, `<input type="checkbox" id="available-only">`, `<input type="checkbox" id="not-wrapped">`); a results container; a small "no data" empty state.
- **`app.js`** — on load, `fetch('data/index.json')` → populate the select, each option labelled `"{model} ({firmware}) — {available_count} available"`. On select change, `fetch('data/devices/<id>.json')` → render services as sections (sorted), each method a row showing:
  - a **status** badge (available / needs-params / absent / other / unreachable),
  - a **risk** badge (read / write / dangerous / active),
  - a **coverage** badge — `✅ gli4py: <method>` when `covered_by` is set, else `⚠️ not yet wrapped`.
  Clicking a row **expands** to show `params` (if any) and the `schema` (pretty-printed). Filters apply client-side: `search` matches service or method substring; `available-only` shows only present methods (available/needs-params); `not-wrapped` shows only present + uncovered. Filters compose. A live count ("showing N methods") updates as filters change. No framework — `fetch` + DOM only.
- **`style.css`** — minimal clean styling; badges colour-coded (risk: read=green, write=amber, dangerous=red; status: available=green, absent=grey; coverage: wrapped=blue, not-yet=amber).

The site is fully static and self-contained; it works under any path prefix (relative `data/` fetches), so the project-pages subpath (`/<repo>/`) needs no config.

## 6. Deploy — GitHub Actions Pages

`.github/workflows/pages.yml` uploads the `site/` directory and deploys it:

```yaml
name: Pages
on:
  push:
    branches: [master, dev]
  workflow_dispatch:
permissions:
  pages: write
  id-token: write
  contents: read
concurrency:
  group: pages
  cancel-in-progress: true
jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deploy.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site
      - id: deploy
        uses: actions/deploy-pages@v4
```

It serves **only** `site/` (the committed sanitized data + static assets) — `docs/superpowers/` is never published. The workflow does **not** run the build script (raw reports aren't in CI); `site/data/` is committed pre-built. Enabling Pages with source = "GitHub Actions" is a one-time repo setting (`gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow`, or Settings → Pages); the workflow only publishes once that's enabled and the deploy branch is pushed. Existing workflows (ci/pylint/codeql/dependency-review/python-publish) are untouched.

## 7. Sample data + local preview

Run `python scripts/build_site_data.py` against the current `docs/devices/mt6000_4.9.0.json` and commit the resulting **sanitized** `site/data/index.json` + `site/data/devices/mt6000_4.9.0.json` so the site renders real content on first load. Local preview: `python -m http.server -d site` → open `http://localhost:8000`.

## 8. Testing

- `tests/test_site_build.py` (pytest, hardware-free): `project_report` on a fixture report **drops `mac`/`sn`/`sn_bak` and all method `value`s**, keeps the device allowlist + method fields, and adds `id`; `build_manifest` computes `service_count`/`available_count`/`not_wrapped_count` correctly (incl. needs-params counting as present and covered methods excluded from not-wrapped). A guard test asserts no `mac`/`sn`/`value` key survives projection (the publish-safety invariant).
- `scripts/build_site_data.py` and its test must be `ruff` + `pylint` clean (both are picked up by `git ls-files '*.py'`). `mypy --strict` targets `gli4py` only, so it does not check `scripts/` — but the script is fully type-annotated regardless.
- The frontend is verified by loading the built site locally (no JS test tooling — YAGNI for a dependency-free static page).

## 9. File structure

| File | Responsibility |
|---|---|
| `scripts/build_site_data.py` | Sanitizing projection: raw reports → `site/data/{index.json, devices/*.json}`. |
| `site/index.html` | Page structure: model select + filter bar + results container. |
| `site/app.js` | Load manifest/device data, render, client-side search + filter toggles + row expand. |
| `site/style.css` | Minimal styling + colour-coded badges. |
| `site/data/index.json` | Committed manifest (sample). |
| `site/data/devices/mt6000_4.9.0.json` | Committed sanitized sample device. |
| `.github/workflows/pages.yml` | GitHub Actions Pages deploy of `site/`. |
| `tests/test_site_build.py` | Projection + manifest + publish-safety tests. |

## 10. Branch

A new branch for the site (decided at implementation kickoff). It needs only the committed sanitized data, not the enumerator code, so it can branch off **`dev`** (independent) or stack on **`feat/api-enumerator`** (keeps it with the related enumerator work, whose output it renders). Default recommendation: stack on `feat/api-enumerator` since the sample data is its output and the two ship together.
