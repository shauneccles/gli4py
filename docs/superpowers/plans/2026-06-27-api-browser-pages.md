# GL.iNet API browser (GitHub Pages) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static GitHub Pages site that renders the enumerator's captured reports as a per-model API browser (pick a model+firmware → see services→methods with status/risk/coverage + filters).

**Architecture:** A local Python build step projects raw `docs/devices/*.json` reports into a sanitized published dataset (`site/data/`), dropping device identifiers and response values. A dependency-free vanilla HTML/JS/CSS page loads that dataset and renders a filterable per-model browser. A GitHub Actions workflow deploys `site/` to Pages.

**Tech Stack:** Python 3.11 stdlib (build script), vanilla HTML/CSS/JS (no framework/bundler), pytest, ruff, pylint, GitHub Actions Pages, uv.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-27-api-browser-pages-design.md`.
- **Publish-safety (hard):** the published dataset keeps ONLY device fields `{model, firmware_version, vendor, device_type, hardware_version}` and per-method `{status, error_code, risk, discovered_by, covered_by, params, schema}`. It **drops `mac`, `sn`, `sn_bak`** (and every other device field) and **every method `value`**. No `mac`/`sn`/`value` may survive projection.
- **"Present"** = `status` in `{"available", "needs_params"}` (matches the enumerator's report renderer).
- Vanilla HTML/JS/CSS only — no framework, no bundler, no npm. Site fetches are **relative** (`data/...`) so it works under the project-pages subpath.
- `scripts/*.py` and `tests/*.py` must be `ruff` clean and `pylint` clean (both are matched by `git ls-files '*.py'`, the CI pylint command). `mypy --strict` targets `gli4py` only (it does NOT check `scripts/`), but the build script is fully type-annotated regardless.
- Raw reports are **never committed** — `docs/devices/` is gitignored; only the sanitized `site/data/` is committed.
- Deploy serves ONLY `site/` (via Actions); `docs/superpowers/` is never published.
- Commands run via uv; new test files start with `# pylint: disable=missing-function-docstring,redefined-outer-name`.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/build_site_data.py` | Sanitizing projection: raw reports → `site/data/{index.json, devices/*.json}`. Stdlib only. |
| `tests/test_site_build.py` | `project_report` / `build_manifest` / `build` + publish-safety tests. |
| `site/index.html` | Page structure: model select + filter bar + results container. |
| `site/style.css` | Minimal styling + colour-coded badges. |
| `site/app.js` | Load manifest/device data, render, client-side search + filter toggles + row expand. |
| `tests/test_site_static.py` | Structural smoke: required element ids, data fetch paths, sample data present + sanitized. |
| `site/data/index.json`, `site/data/devices/<id>.json` | Committed sanitized sample (built from the live report). |
| `.github/workflows/pages.yml` | GitHub Actions Pages deploy of `site/`. |
| `.gitignore` | Add `docs/devices/` (raw reports never committed). |

---

### Task 1: Build script (sanitizing projection + manifest + CLI)

**Files:**
- Create: `scripts/build_site_data.py`
- Test: `tests/test_site_build.py`

**Interfaces:**
- Produces:
  - `project_report(raw: dict, device_id_str: str) -> dict` — sanitized per-device surface (`id` + device allowlist + `services` with `value` dropped).
  - `build_manifest(devices: list[dict]) -> dict` — `{"devices": [{id, model, firmware_version, service_count, available_count, not_wrapped_count}]}`.
  - `build(reports_dir: Path, out_dir: Path) -> int` — read `reports_dir/*.json`, write `out_dir/index.json` + `out_dir/devices/<stem>.json`, return device count.
  - `main(argv: list[str] | None = None) -> int` — CLI (`--reports docs/devices`, `--out site/data`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_site_build.py`:

```python
"""Tests for the Pages site dataset build (sanitizing projection)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import json

from scripts.build_site_data import build, build_manifest, project_report

RAW = {
    "device": {
        "model": "mt6000", "firmware_version": "4.9.0", "vendor": "GL.iNet",
        "device_type": "router", "hardware_version": "1.0",
        "mac": "94:83:C4:AA:BB:CC", "sn": "SECRET123", "sn_bak": "SECRET456",
        "country_code": "US", "hidden_features": [],
    },
    "services": {
        "system": {
            "get_info": {
                "status": "available", "error_code": None, "risk": "read",
                "discovered_by": "catalog", "covered_by": "router_info",
                "params": None, "schema": {"model": "str"},
                "value": {"mac": "94:83:C4:AA:BB:CC", "sn": "SECRET123"},
            },
        },
        "firewall": {
            "get_rule_list": {
                "status": "available", "error_code": None, "risk": "read",
                "discovered_by": "catalog", "covered_by": None,
                "params": None, "schema": {"res": "list"}, "value": {"res": []},
            },
            "set_rule": {
                "status": "absent", "error_code": -32601, "risk": "write",
                "discovered_by": "catalog", "covered_by": None,
                "params": None, "schema": None, "value": None,
            },
        },
    },
}


def test_project_keeps_allowlist_and_method_fields():
    out = project_report(RAW, "mt6000_4.9.0")
    assert out["id"] == "mt6000_4.9.0"
    assert out["model"] == "mt6000"
    assert out["firmware_version"] == "4.9.0"
    assert out["vendor"] == "GL.iNet"
    m = out["services"]["system"]["get_info"]
    assert m["status"] == "available"
    assert m["covered_by"] == "router_info"
    assert m["schema"] == {"model": "str"}


def test_project_drops_identifiers_and_values():
    out = project_report(RAW, "mt6000_4.9.0")
    for k in ("mac", "sn", "sn_bak", "country_code", "hidden_features"):
        assert k not in out
    assert "value" not in out["services"]["system"]["get_info"]
    blob = json.dumps(project_report(RAW, "mt6000_4.9.0"))
    assert "SECRET123" not in blob and "SECRET456" not in blob
    assert "94:83:C4" not in blob
    assert '"value"' not in blob


def test_build_manifest_counts():
    dev = project_report(RAW, "mt6000_4.9.0")
    entry = build_manifest([dev])["devices"][0]
    assert entry["id"] == "mt6000_4.9.0"
    assert entry["available_count"] == 2   # system.get_info + firewall.get_rule_list
    assert entry["service_count"] == 2     # both services have a present method
    assert entry["not_wrapped_count"] == 1 # firewall.get_rule_list (covered_by None)


def test_build_writes_sanitized_files(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "mt6000_4.9.0.json").write_text(json.dumps(RAW), encoding="utf-8")
    out = tmp_path / "out"
    assert build(reports, out) == 1
    manifest = json.loads((out / "index.json").read_text(encoding="utf-8"))
    assert manifest["devices"][0]["model"] == "mt6000"
    dev = json.loads((out / "devices" / "mt6000_4.9.0.json").read_text(encoding="utf-8"))
    assert "mac" not in dev
    assert '"value"' not in json.dumps(dev)


def test_build_empty_reports(tmp_path):
    out = tmp_path / "out"
    assert build(tmp_path / "nonexistent", out) == 0
    assert json.loads((out / "index.json").read_text(encoding="utf-8")) == {"devices": []}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_site_build.py -v`
Expected: `ModuleNotFoundError: No module named 'scripts.build_site_data'`.

- [ ] **Step 3: Create the build script**

Create `scripts/build_site_data.py`:

```python
"""Build the sanitized GitHub Pages dataset from enumerator reports.

Reads docs/devices/*.json (raw, may contain device identifiers + response
values) and writes site/data/index.json + site/data/devices/<id>.json
containing ONLY the publishable API surface: model + firmware + per-method
shape. No mac/sn/sn_bak, no response values are emitted.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Device fields safe to publish (identifiers like mac/sn are NOT here).
_DEVICE_FIELDS = ("model", "firmware_version", "vendor", "device_type", "hardware_version")
# Per-method fields to publish (response "value" is deliberately excluded).
_METHOD_FIELDS = ("status", "error_code", "risk", "discovered_by", "covered_by", "params", "schema")
_PRESENT = ("available", "needs_params")


def project_report(raw: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """Project a raw enumerator report to the publishable, sanitized surface."""
    device = raw.get("device", {})
    out: dict[str, Any] = {"id": device_id_str}
    for field in _DEVICE_FIELDS:
        if field in device:
            out[field] = device[field]
    out["services"] = {
        service: {
            method: {field: rec.get(field) for field in _METHOD_FIELDS}
            for method, rec in methods.items()
        }
        for service, methods in raw.get("services", {}).items()
    }
    return out


def build_manifest(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the manifest: per-device id/model/firmware + present-method counts."""
    entries: list[dict[str, Any]] = []
    for dev in devices:
        present = [
            rec
            for methods in dev["services"].values()
            for rec in methods.values()
            if rec.get("status") in _PRESENT
        ]
        service_count = sum(
            1
            for methods in dev["services"].values()
            if any(rec.get("status") in _PRESENT for rec in methods.values())
        )
        entries.append(
            {
                "id": dev["id"],
                "model": dev.get("model", "unknown"),
                "firmware_version": dev.get("firmware_version", "unknown"),
                "service_count": service_count,
                "available_count": len(present),
                "not_wrapped_count": sum(1 for rec in present if rec.get("covered_by") is None),
            }
        )
    entries.sort(key=lambda entry: (entry["model"], entry["firmware_version"]))
    return {"devices": entries}


def build(reports_dir: Path, out_dir: Path) -> int:
    """Read reports_dir/*.json, write out_dir/index.json + devices/<stem>.json."""
    devices_out = out_dir / "devices"
    devices_out.mkdir(parents=True, exist_ok=True)
    report_paths = sorted(reports_dir.glob("*.json")) if reports_dir.exists() else []
    projected: list[dict[str, Any]] = []
    for report_path in report_paths:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        dev = project_report(raw, report_path.stem)
        projected.append(dev)
        (devices_out / f"{report_path.stem}.json").write_text(
            json.dumps(dev, indent=2, sort_keys=True), encoding="utf-8"
        )
    (out_dir / "index.json").write_text(
        json.dumps(build_manifest(projected), indent=2, sort_keys=True), encoding="utf-8"
    )
    return len(projected)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Build the Pages API dataset from enumerator reports.")
    parser.add_argument("--reports", default="docs/devices")
    parser.add_argument("--out", default="site/data")
    args = parser.parse_args(argv)
    count = build(Path(args.reports), Path(args.out))
    print(f"Wrote {count} device(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_site_build.py -v`
Expected: PASS (5 passed). If the import fails because `scripts` is not importable, create an empty `scripts/__init__.py` containing only `"""Repo build/maintenance scripts."""` and re-run.

- [ ] **Step 5: Lint and commit**

Run: `uv run ruff check scripts tests && uv run ruff format scripts tests && uv run --with pylint pylint --disable=import-error,fixme,line-too-long,invalid-name,too-many-public-methods,abstract-method,overridden-final-method,too-many-instance-attributes,too-many-public-methods,too-few-public-methods,too-many-branches scripts/build_site_data.py tests/test_site_build.py`
Expected: ruff clean; pylint `10.00`.
```bash
git add scripts/build_site_data.py tests/test_site_build.py
git commit -m "feat(site): sanitizing build script for the Pages API dataset"
```

---

### Task 2: Generate + commit sample data; gitignore raw reports

**Files:**
- Create (generated): `site/data/index.json`, `site/data/devices/mt6000_4.9.0.json`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `scripts/build_site_data.py` (Task 1); the local raw report `docs/devices/mt6000_4.9.0.json` (present on disk, uncommitted).

- [ ] **Step 1: Gitignore raw reports (publish-safety)**

Append to `.gitignore`:
```
# Raw enumerator reports may contain device identifiers (mac/sn) — never commit;
# only the sanitized site/data/ projection is published.
docs/devices/
```

- [ ] **Step 2: Build the sample dataset**

Run: `uv run python scripts/build_site_data.py`
Expected: `Wrote 1 device(s) to site/data` (it reads `docs/devices/mt6000_4.9.0.json`). If that report is missing, run `uv run gli4py-enumerate` first (read-only) to produce it.

- [ ] **Step 3: Verify the committed data is sanitized**

Run:
```bash
uv run python -c "import json,glob; [print(f, 'mac' in (d:=json.load(open(f))), '\"value\"' in json.dumps(d)) for f in glob.glob('site/data/devices/*.json')]"
grep -RiE '\"(mac|sn|sn_bak|value)\"' site/data && echo 'LEAK!' || echo 'clean (no identifiers/values)'
```
Expected: each device prints `... False False`; the grep prints `clean (no identifiers/values)`.

- [ ] **Step 4: Confirm raw reports are ignored**

Run: `git check-ignore docs/devices/mt6000_4.9.0.json`
Expected: prints the path (ignored). `git status --short docs/devices/` shows nothing.

- [ ] **Step 5: Commit the sanitized sample + gitignore**

```bash
git add .gitignore site/data
git commit -m "feat(site): sanitized sample dataset (mt6000_4.9.0); gitignore raw reports"
```

---

### Task 3: Static site (HTML + CSS + JS) + structural smoke test

**Files:**
- Create: `site/index.html`, `site/style.css`, `site/app.js`
- Test: `tests/test_site_static.py`

**Interfaces:**
- Consumes: `site/data/index.json` + `site/data/devices/<id>.json` (Task 2).

- [ ] **Step 1: Write the failing structural test**

Create `tests/test_site_static.py`:

```python
"""Structural smoke checks for the static API browser site."""
# pylint: disable=missing-function-docstring

import json
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"


def test_index_html_has_controls():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    for needle in (
        'id="device"', 'id="search"', 'id="available-only"',
        'id="not-wrapped"', 'id="results"', "app.js", "style.css",
    ):
        assert needle in html, needle


def test_app_js_fetches_relative_data_paths():
    js = (SITE / "app.js").read_text(encoding="utf-8")
    assert "data/index.json" in js
    assert "data/devices/" in js


def test_sample_data_present_and_sanitized():
    manifest = json.loads((SITE / "data" / "index.json").read_text(encoding="utf-8"))
    assert manifest["devices"], "expected committed sample data"
    for entry in manifest["devices"]:
        dev = json.loads((SITE / "data" / "devices" / f"{entry['id']}.json").read_text(encoding="utf-8"))
        assert "mac" not in dev and "sn" not in dev and "sn_bak" not in dev
        assert '"value"' not in json.dumps(dev)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_site_static.py -v`
Expected: FAIL (`site/index.html` does not exist).

- [ ] **Step 3: Create `site/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GL.iNet API browser</title>
  <link rel="stylesheet" href="style.css">
</head>
<body>
  <header>
    <h1>GL.iNet API browser</h1>
    <p class="sub">Discovered RPC surface per device, from <code>gli4py-enumerate</code>.</p>
  </header>
  <div class="controls">
    <label class="field">Model
      <select id="device"></select>
    </label>
    <input id="search" type="search" placeholder="filter service / method…">
    <label class="chk"><input type="checkbox" id="available-only"> available only</label>
    <label class="chk"><input type="checkbox" id="not-wrapped"> not yet wrapped</label>
    <span id="count" class="count"></span>
  </div>
  <main id="results"></main>
  <footer>
    <p>Built from sanitized enumerator reports — no device identifiers or response values are published.</p>
  </footer>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Create `site/style.css`**

```css
:root {
  --bg: #0f1419; --panel: #1a212b; --fg: #e6e9ef; --muted: #9aa6b2; --line: #2a3340;
  --green: #2ea043; --amber: #d29922; --red: #da3633; --blue: #2f81f7;
}
* { box-sizing: border-box; }
body { margin: 0; font: 14px/1.5 system-ui, sans-serif; background: var(--bg); color: var(--fg); }
header, .controls, main, footer { max-width: 1000px; margin: 0 auto; padding: 0 16px; }
header { padding-top: 24px; }
h1 { margin: 0 0 4px; font-size: 22px; }
.sub, footer { color: var(--muted); font-size: 13px; }
code { background: var(--panel); padding: 1px 5px; border-radius: 4px; }
.controls { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin: 18px auto; }
.field { display: flex; gap: 6px; align-items: center; }
select, #search { background: var(--panel); color: var(--fg); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 8px; font: inherit; }
#search { flex: 1; min-width: 180px; }
.chk { color: var(--muted); display: flex; gap: 4px; align-items: center; }
.count { color: var(--muted); margin-left: auto; }
.service { border: 1px solid var(--line); border-radius: 8px; margin: 12px 0; overflow: hidden; }
.service h2 { margin: 0; padding: 8px 12px; font-size: 14px; background: var(--panel); }
.method { padding: 7px 12px; border-top: 1px solid var(--line); cursor: pointer; }
.mhead { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.badge { font-size: 11px; padding: 1px 7px; border-radius: 10px; border: 1px solid transparent; }
.rk-read { background: rgba(46,160,67,.15); color: var(--green); }
.rk-write, .rk-active { background: rgba(210,153,34,.15); color: var(--amber); }
.rk-dangerous { background: rgba(218,54,51,.15); color: var(--red); }
.st-available { background: rgba(46,160,67,.15); color: var(--green); }
.st-needs_params { background: rgba(210,153,34,.15); color: var(--amber); }
.st-absent, .st-unreachable, .st-other, .st-auth_error, .st-token_error {
  background: var(--panel); color: var(--muted); }
.cov-yes { background: rgba(47,129,247,.15); color: var(--blue); }
.cov-no { background: rgba(210,153,34,.12); color: var(--amber); }
.detail { display: none; margin: 8px 0 2px; background: #0b0f14; border: 1px solid var(--line);
  border-radius: 6px; padding: 8px; font-size: 12px; overflow-x: auto; white-space: pre; }
.method.open .detail { display: block; }
.empty { color: var(--muted); padding: 24px 0; }
```

- [ ] **Step 5: Create `site/app.js`**

```javascript
"use strict";

const els = {
  device: document.getElementById("device"),
  search: document.getElementById("search"),
  availableOnly: document.getElementById("available-only"),
  notWrapped: document.getElementById("not-wrapped"),
  count: document.getElementById("count"),
  results: document.getElementById("results"),
};

const PRESENT = new Set(["available", "needs_params"]);
let current = null;

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function badge(text, cls) {
  return `<span class="badge ${cls}">${escapeHtml(String(text))}</span>`;
}

function methodRow(service, method, rec) {
  const present = PRESENT.has(rec.status);
  let cov = "";
  if (rec.covered_by) cov = badge(`gli4py: ${rec.covered_by}`, "cov-yes");
  else if (present) cov = badge("not yet wrapped", "cov-no");
  let detail = "";
  if (rec.params || rec.schema) {
    const body = JSON.stringify({ params: rec.params, schema: rec.schema }, null, 2);
    detail = `<pre class="detail">${escapeHtml(body)}</pre>`;
  }
  return `<div class="method">
    <div class="mhead">
      <code>${escapeHtml(method)}</code>
      ${badge(rec.status, "st-" + rec.status)}
      ${badge(rec.risk, "rk-" + rec.risk)}
      ${cov}
    </div>${detail}</div>`;
}

function render() {
  if (!current) return;
  const q = els.search.value.trim().toLowerCase();
  const availOnly = els.availableOnly.checked;
  const nw = els.notWrapped.checked;
  let shown = 0;
  const parts = [];
  for (const service of Object.keys(current.services).sort()) {
    const methods = current.services[service];
    const rows = [];
    for (const method of Object.keys(methods).sort()) {
      const rec = methods[method];
      const present = PRESENT.has(rec.status);
      if (availOnly && !present) continue;
      if (nw && !(present && rec.covered_by == null)) continue;
      if (q && !`${service}.${method}`.toLowerCase().includes(q)) continue;
      rows.push(methodRow(service, method, rec));
      shown += 1;
    }
    if (rows.length) parts.push(`<section class="service"><h2>${escapeHtml(service)}</h2>${rows.join("")}</section>`);
  }
  els.results.innerHTML = parts.join("") || "<p class='empty'>No methods match.</p>";
  els.count.textContent = `${shown} method${shown === 1 ? "" : "s"}`;
}

async function loadDevice(id) {
  const res = await fetch(`data/devices/${id}.json`);
  current = await res.json();
  render();
}

async function loadManifest() {
  let manifest;
  try {
    manifest = await (await fetch("data/index.json")).json();
  } catch (err) {
    els.results.innerHTML = "<p class='empty'>Could not load data/index.json.</p>";
    return;
  }
  if (!manifest.devices || !manifest.devices.length) {
    els.results.innerHTML = "<p class='empty'>No device data yet. Run <code>gli4py-enumerate</code> then <code>scripts/build_site_data.py</code>.</p>";
    return;
  }
  for (const d of manifest.devices) {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = `${d.model} (${d.firmware_version}) — ${d.available_count} available`;
    els.device.appendChild(opt);
  }
  await loadDevice(manifest.devices[0].id);
}

els.device.addEventListener("change", (e) => loadDevice(e.target.value));
for (const el of [els.search, els.availableOnly, els.notWrapped]) {
  el.addEventListener("input", render);
}
els.results.addEventListener("click", (e) => {
  const m = e.target.closest(".method");
  if (m) m.classList.toggle("open");
});

loadManifest();
```

- [ ] **Step 6: Run the structural test + load the site locally**

Run: `uv run pytest tests/test_site_static.py -v`
Expected: PASS (3 passed).

Then serve and sanity-check it responds:
```bash
( cd site && python -m http.server 8137 >/dev/null 2>&1 & echo $! > /tmp/site.pid )
sleep 1
curl -s -o /dev/null -w "index.html %{http_code}\n" http://localhost:8137/
curl -s -o /dev/null -w "data/index.json %{http_code}\n" http://localhost:8137/data/index.json
kill "$(cat /tmp/site.pid)"
```
Expected: both `200`. (Visual rendering — the dropdown, badges, filters — is verified by the controller opening the page; there is no JS test tooling per the spec.)

- [ ] **Step 7: Lint and commit**

Run: `uv run ruff check tests && uv run --with pylint pylint --disable=import-error,fixme,line-too-long,invalid-name,too-many-public-methods,abstract-method,overridden-final-method,too-many-instance-attributes,too-many-public-methods,too-few-public-methods,too-many-branches tests/test_site_static.py`
Expected: clean / `10.00`.
```bash
git add site/index.html site/style.css site/app.js tests/test_site_static.py
git commit -m "feat(site): static per-model API browser (dropdown + filters + expand)"
```

---

### Task 4: GitHub Actions Pages deploy

**Files:**
- Create: `.github/workflows/pages.yml`

**Interfaces:**
- Consumes: the committed `site/` directory (Tasks 2–3).

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/pages.yml`:

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

- [ ] **Step 2: Validate the YAML**

Run: `uv run python -c "import yaml; yaml.safe_load(open('.github/workflows/pages.yml')); print('ok')"`
Expected: `ok`.

> The workflow uploads the committed `site/` directory only (it does NOT run the build script — `site/data/` is pre-built and committed). It deploys once Pages is enabled with source = "GitHub Actions": `gh api -X POST repos/<owner>/<repo>/pages -f build_type=workflow` (or Settings → Pages → Build and deployment → GitHub Actions). The other workflows (ci/pylint/codeql/dependency-review/python-publish) are untouched.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pages.yml
git commit -m "ci(site): deploy site/ to GitHub Pages via Actions"
```

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| Sanitizing projection (allowlist device fields; drop value) | 1 |
| Publish-safety: no mac/sn/value survives | 1 (tests) + 2 (verify) + 3 (committed-data test) |
| Manifest with counts (service/available/not-wrapped) | 1 |
| "Present" = available + needs_params | 1 (counts), 3 (filters) |
| Per-model browser: dropdown + services→methods + badges | 3 |
| Filters: search, available-only, not-wrapped | 3 |
| Per-method params+schema expand | 3 |
| Vanilla, relative fetches, no framework | 3 |
| Committed sanitized sample data | 2 |
| Raw reports never committed (gitignore) | 2 |
| Actions Pages deploy of site/ only | 4 |
| ruff + pylint clean (scripts + tests) | 1,3 (lint steps) |
| Local preview | 3 (step 6) |

No uncovered requirements. The cross-model matrix is explicitly out of scope (spec §1).

**2. Placeholder scan:** No TBD/TODO. The site's visual rendering is verified by the controller opening the page (the spec states no JS test tooling — YAGNI); the structural test + HTTP 200 checks are the automated gate. Not a placeholder.

**3. Type consistency:** `project_report(raw, device_id_str)`, `build_manifest(devices)`, `build(reports_dir, out_dir)`, `main(argv)` are used with identical signatures in Task 1's code and tests. The published per-device keys (`id`, `model`, `firmware_version`, `vendor`, `device_type`, `hardware_version`, `services`) and method fields (`status`, `error_code`, `risk`, `discovered_by`, `covered_by`, `params`, `schema`) match between the build script (Task 1), the sample data (Task 2), and `app.js` (Task 3, which reads `rec.status`/`rec.risk`/`rec.covered_by`/`rec.params`/`rec.schema` and manifest `model`/`firmware_version`/`available_count`/`id`). The HTML element ids (`device`, `search`, `available-only`, `not-wrapped`, `results`, `count`) match between `index.html`, `app.js`, and `tests/test_site_static.py`.

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (`superpowers:subagent-driven-development`).
2. **Inline Execution** — work the tasks in this session with checkpoints (`superpowers:executing-plans`).
