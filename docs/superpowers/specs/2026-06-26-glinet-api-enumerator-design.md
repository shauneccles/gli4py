# Design: GL.iNet device API enumerator

- **Date:** 2026-06-26
- **Status:** Approved (design); pending implementation plan
- **Branch:** `feat/api-enumerator` (off `feat/api-transport-boundary` @ `36efcf7` — depends on the refactored typed `GLinet` client)
- **Supports:** issue #2 (expand API surface) — the enumerator reveals which endpoints a given device exposes, so we know what to wrap next.

## 1. Goal & scope

A **shipped** CLI (`gli4py-enumerate`) that points at the GL.iNet device configured in `.env`, discovers which RPC services/methods it actually exposes, and emits a clear per-device "API exposure" artifact (JSON + Markdown) plus a terminal summary. It is strictly **read-only**.

In scope:
- Catalog-driven probing of known GL.iNet services × read-only methods.
- Classification of each probe (available / absent / needs-params / auth-error / other).
- Capture of response **values with secret redaction by default**; a `--unredacted` flag captures raw values.
- Annotation of which `(service, method)` pairs `gli4py` already wraps (gap analysis for #2).
- JSON + Markdown artifacts under `docs/devices/`.

Out of scope: any mutating call; auto-running in CI; changing the `gli4py` library API (the tool reuses `GLinet` as a consumer only).

## 2. Background — probe findings (verified against a live device)

Probed a real device (firmware `release`, host `http://192.168.1.1`) read-only:

- **No live introspection.** A top-level `list` method (any param shape) returns `-32601 "Method not found"`. The GL.iNet gateway whitelists `challenge`/`login`/`call` but not ubus introspection — so single-call discovery is impossible.
- **Uniform absent signature.** A bogus *service* (`__nope__ get_status`) and a bogus *method* (`system __nope__`) both return `-32601 "Method not found"`. This cleanly separates absent from available.
- **`-32602 "Invalid params"`** means the method exists but needs arguments (still useful: the endpoint is present).
- **Catalog probing genuinely discovers the surface.** Confirmed available on the test device: `tor`, `ovpn-server`, `wg-server`, `led` (`get_config`), `repeater`, `tethering`, `adguardhome`, `ddns`, plus the `system`/`clients`/`wifi`/`wg-client`/`vpn-client`/`tailscale` services gli4py already uses. `ovpn-client get_status`, `mwan`, `modem`, `led get_status`, `firmware check` returned `-32601` (wrong method name or absent on that model — confirming method names vary and we must try several read verbs per service).
- **Responses can contain secrets.** `wg-server get_config` exposes `private_key`; `ddns get_config` exposes `device_id`. Redaction of committed artifacts is mandatory.

## 3. Approach

Catalog-driven read-only probing:

1. Authenticate with `gli4py`'s `GLinet.login()` (reuses the challenge/response hashing — no crypto reimplementation) to obtain a `sid`.
2. For each `(service, method)` in the catalog (curated methods **plus** a `COMMON_READ_METHODS` set tried against every service), issue a **raw** `call` POST and read the full JSON-RPC envelope (so error codes are visible — `GLinet.request` raises and hides them, so the tool posts raw).
3. Classify each result; for available ones, capture the response value with redaction.
4. Annotate gli4py coverage.
5. Render JSON + Markdown + terminal summary.

## 4. Package layout

The tool ships inside the package as a small, focused subpackage. Every file meets the repo's quality bars (`mypy --strict`, `ruff`, `pylint`, `py.typed`).

| File | Responsibility |
|---|---|
| `gli4py/enumerator/__init__.py` | Package marker; re-export `enumerate_device` and key types. |
| `gli4py/enumerator/catalog.py` | `CATALOG: dict[str, list[str]]` (service → known read methods), `COMMON_READ_METHODS: list[str]`, and `READ_VERB_ALLOWLIST` (regex/prefixes for the safety net). Pure data. |
| `gli4py/enumerator/coverage.py` | `GLI4PY_COVERAGE: dict[tuple[str, str], str]` — `(service, method) → wrapping GLinet method name`. Hand-maintained from `glinet.py`. |
| `gli4py/enumerator/classify.py` | Pure: `classify(envelope) -> ProbeResult` using the observed codes (`-32601`→ABSENT, `-32602`→NEEDS_PARAMS, `-32000`→AUTH_ERROR, has `result`→AVAILABLE, else OTHER). |
| `gli4py/enumerator/redact.py` | Pure: `redact(value, *, enabled) -> value` — deep copy with secret-looking field values replaced by `"<redacted>"`. |
| `gli4py/enumerator/probe.py` | `async enumerate_device(...) -> DeviceReport` — login, raw probing loop, assembly. The only I/O unit. |
| `gli4py/enumerator/report.py` | Pure: `to_json(report)` / `to_markdown(report)` / `summary_lines(report)`. |
| `gli4py/enumerator/cli.py` | `main()` — argparse, `.env` loading (optional), wiring, file writing, exit codes. Console entry point. |

## 5. Classification rules (from observed envelopes)

```
has "result"                         -> AVAILABLE          (capture redacted value + shape)
error.code == -32601                 -> ABSENT             ("Method not found")
error.code == -32602                 -> NEEDS_PARAMS       (exists; needs args)
error.code == -32000                 -> AUTH_ERROR         (session/permission)
error.code == -1                     -> TOKEN_ERROR        (expired sid)
any other error.code                 -> OTHER(code, msg)
transport exception                  -> UNREACHABLE(detail)
```

`NEEDS_PARAMS` counts as "present" in the available/not-yet-wrapped gap analysis.

## 6. Redaction & `--unredacted`

- **Default (redacted):** captured response values are deep-copied with the value of any key matching a case-insensitive denylist replaced by `"<redacted>"`. Seed denylist: `password`, `passwd`, `pwd`, `key`, `psk`, `secret`, `private_key`, `privatekey`, `token`, `sid`, `hash`, `nonce`, `salt`, `device_id`. As a second safety net, very long opaque strings (≥ 64 chars, base64/hex-looking) are redacted regardless of key. Redaction is best-effort; the Markdown header notes "review before committing."
- **`--unredacted`:** disables all redaction and captures raw values. The CLI prints a prominent warning that the output contains secrets and **must not be committed**, and defaults its output directory to a non-`docs/` path (caller must pass `--output-dir`); these files are not written under `docs/devices/` unless explicitly forced.
- Both modes always also record the response **schema** (keys → value types, depth-limited), which is inherently secret-free and is the primary "API exposure" signal.

## 7. Read-only safety (hard requirement)

Two layers: (1) the catalog contains only read methods; (2) `probe.py` asserts every method matches `READ_VERB_ALLOWLIST` (e.g. starts with `get_`, or in `{check, status, list, info}`-style) and refuses anything matching mutating verbs (`set_`, `start`, `stop`, `add`, `del`, `delete`, `enable`, `disable`, `reboot`, `update`, `apply`, `create`, `remove`). A catalog entry that fails the allowlist aborts with an error rather than being probed.

## 8. Output artifacts

Per device, `device_id` is a slugified `f"{model}_{firmware_version}"`, where `model` is resolved from `system get_info` as the first present of `model` → `device_type` → `board_info` → `"unknown"`, and `firmware_version` falls back to `"unknown"` if absent:
- **`docs/devices/<device_id>.json`** — `{device: {...metadata}, services: {service: {method: {status, error_code, schema, value (redacted), covered_by: <glinet method|null>}}}}`. Machine-readable and diffable across devices.
- **`docs/devices/<device_id>.md`** — human-readable: a metadata header, a per-service availability table, and an **"Available but not yet wrapped by gli4py"** section (the #2 worklist).
- **Terminal summary** — counts (available / absent / needs-params), and the not-yet-wrapped list.

## 9. Config & auth

- Inputs resolved in order: CLI flags (`--host`, `--username`, `--password`, `--env-file`) → environment variables (`GLINET_HOST`, `GLINET_USERNAME`, `GLINET_PASSWORD`) → `.env` (auto-loaded if `python-dotenv` is importable).
- `.env` support is delivered via an optional extra: `pip install gli4py[cli]` pulls `python-dotenv`. The core runtime deps are unchanged (the just-completed lean wheel is preserved). `cli.py` lazy-imports `dotenv` and, if absent, prints a one-line hint and falls back to env vars / flags.
- Auth reuses `GLinet.login()`. Probing uses a raw `aiohttp` POST (aiohttp is already a runtime dep) so error envelopes are visible.

## 10. Packaging

- `pyproject.toml`: add `[project.scripts]` `gli4py-enumerate = "gli4py.enumerator.cli:main"`; add `[project.optional-dependencies]` `cli = ["python-dotenv>=1.0"]`.
- The subpackage ships in the wheel (it is under `gli4py/`); `py.typed` already covers it.
- The code is `mypy --strict` clean, `ruff` clean, and `pylint` clean (it is included by `git ls-files '*.py'` and the `gli4py` mypy target). The existing CI (ruff + mypy + pytest; pylint) gates it automatically — no workflow changes needed.

## 11. Testing

Pure units get hardware-free unit tests (`tests/test_enumerator.py`, transport-mocked where needed):
- `classify`: each observed envelope (`result`, `-32601`, `-32602`, `-32000`, `-1`, other, exception) → correct category.
- `redact`: a dict containing `private_key`/`device_id`/`key`/a long base64 string → those values become `"<redacted>"`, non-secret values (`status`, `enable`, `ssid`) preserved; `--unredacted` path leaves all values intact.
- `coverage`: a `(service, method)` known to gli4py maps to the right wrapping method; an unknown pair maps to `None`.
- `report`: a small `DeviceReport` → expected JSON keys and Markdown sections (incl. the not-yet-wrapped list).
- `READ_VERB_ALLOWLIST`: mutating verbs rejected; read verbs accepted.
- `enumerate_device`: against a mocked raw-POST layer, end-to-end assembly produces the expected `DeviceReport` (no hardware).

The live run is manual (needs a device) and not in CI — same pattern as the existing live tests.

## 12. Open follow-ups (non-blocking)

- Grow the catalog as new devices/firmwares are enumerated (each run may reveal `-32601` gaps to fill with alternate method names).
- A future `--diff <other.json>` to compare two devices' surfaces.
- Optionally derive `GLI4PY_COVERAGE` automatically from `glinet.py` later; hand-maintained for now.
