# Design: GL.iNet device API enumerator

- **Date:** 2026-06-26
- **Status:** Approved (design); pending implementation plan
- **Branch:** `feat/api-enumerator` (off `feat/api-transport-boundary` @ `36efcf7` — depends on the refactored typed `GLinet` client)
- **Supports:** issue #2 (expand API surface) — the enumerator reveals which endpoints a given device exposes, so we know what to wrap next.

## 1. Goal & scope

A **shipped** CLI (`gli4py-enumerate`) that points at the GL.iNet device configured in `.env`, discovers which RPC services/methods it actually exposes, and emits a clear per-device "API exposure" artifact (JSON + Markdown) plus a terminal summary. The **default mode is strictly read-only**; aggressive discovery is gated behind explicit `--dangerous` flags.

Three discovery tiers (escalating):
1. **Default — catalog probe (read-only).** Probe a comprehensive curated catalog of GL.iNet services × their *read* methods. Safe, no side effects.
2. **`--discover-acl` (read-only, best-effort).** Attempt to read the rpcd ACL files (`/usr/share/rpcd/acl.d/*.json`) and `uci get rpcd` via the `file`/`uci` namespaces — the *definitive* surface map when permitted. On the gl-ngx gateway this is usually blocked (`-32601`, verified — see §2), so it is opportunistic, not primary.
3. **`--dangerous` / `--dangerous-full` (gated brute-force).** Brute a wordlist of service names × method names to find endpoints the catalog misses, classifying by error code. `--dangerous` tries **read-verbs only**; `--dangerous-full` additionally tries mutating verbs (which may cause side effects — see §13). Rate-limited and opt-in with prominent warnings.

In scope (all tiers):
- Classification of each probe (available / absent / needs-params / auth-error / other).
- A risk-classified catalog: every `(service, method)` tagged READ / WRITE / DANGEROUS.
- Capture of response **values with secret redaction by default**; a `--unredacted` flag captures raw values.
- Annotation of which `(service, method)` pairs `gli4py` already wraps (gap analysis for #2).
- JSON + Markdown artifacts under `docs/devices/`.

Out of scope: mutating calls in the default and `--dangerous` (read-verb) tiers; auto-running in CI; changing the `gli4py` library API (the tool reuses `GLinet` as a consumer only). `--dangerous-full` is the only path that may issue non-read calls, and only with explicit opt-in.

## 2. Background — findings (research + verified against a live device)

### Probe behaviour (live device, firmware `release`, read-only)

- **No live introspection.** A top-level `list` method (any param shape) returns `-32601 "Method not found"`. The gl-ngx gateway whitelists `challenge`/`login`/`call` but not ubus introspection — single-call discovery is impossible.
- **Uniform absent signature.** A bogus *service* (`__nope__ get_status`) and a bogus *method* (`system __nope__`) both return `-32601 "Method not found"`. This cleanly separates absent from available — the core classifier signal.
- **`-32602 "Invalid params"`** means the method exists but needs arguments (still a "present" signal).
- **Raw OpenWRT ubus is NOT exposed.** Verified: `system board`, `system info`, `service list`, `uci get`, `iwinfo devices`, `luci-rpc *`, `rpc-sys packagelist`, `log read`, and the `file` namespace all return `-32601`. The gateway fronts only GL.iNet *application* services, not the underlying ubus objects. (`network.interface dump` returned `-32602` — a lone partial exception.)
- **ACL-file discovery is usually blocked.** `file list /usr/share/rpcd/acl.d` → `-32601` on this device — the `file` namespace is not ACL-permitted to the session role. So `--discover-acl` is best-effort; catalog + brute-force are the real paths.
- **Responses can contain secrets.** `wg-server get_config` → `private_key`; `ddns get_config` → `device_id`. Redaction of committed artifacts is mandatory.

### Catalog research (multi-source)

A research sweep (official-adjacent docs, 10 community integrations, OpenWRT ubus internals) produced a comprehensive surface map:

- **`tomtana/python-glinet` bundles `api_description.json`** — an authoritative ~1.4 MB spec covering **42 services** with full method lists and read/write classification. This is the primary catalog seed.
- Cross-referenced against `HarvsG/gli4py`, `spusuf/glinet_api-hass`, `angolo40/GLiNet_HomeAssistant`, `vithurshanselvarajah/ha-glinet`, `ryanrishi/glinet-client-go`, `cinderblock/homeassistant-glinet`, `CaseyBlackburn/glsms`, and others.
- **~30 services beyond what gli4py wraps**, e.g.: `firewall`, `modem`, `qos`, `dns`/`custom_dns`, `ipv6`, `kmwan` (multi-WAN), `ovpn-client`, `ovpn-server`, `wg-server`, `zerotier`, `tor`, `parental-control`, `adguardhome`, `ddns`, `netmode`, `upgrade`, `plugins`, `cloud`, `s2s`, `rtty`, `black_white_list`, `nas_web`/`samba`/`dlna`, `logread`, `network` (arp/leases/routes), `vpn-policy`, `led`, `fan`, `cable`, `acl`, `ui`, `switch-button`, `rs485` (industrial models), `mcu` (battery/OLED models).
- **Naming quirk:** the spec's internal keys use underscores (`wg_client`); the wire protocol uses hyphens (`wg-client`). The catalog stores the canonical hyphenated form and the prober may try both.
- **Live confirmation:** of 50 catalog services probed read-only, **36 are present** on the test device (incl. ~25 unwrapped by gli4py). This validates the catalog as the discovery engine.

### Implication

Discovery is **catalog-first** (comprehensive, safe), with `--discover-acl` as an opportunistic ground-truth attempt and `--dangerous` brute-force as the way to find anything the catalog misses (e.g. device/firmware-specific services). The catalog seed is large and well-sourced; it ships with the tool and grows over time.

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
| `gli4py/enumerator/catalog.py` | The risk-classified catalog: `CATALOG: dict[str, dict[str, Risk]]` (service → method → `READ`/`WRITE`/`DANGEROUS`), seeded comprehensively from the research (§2), plus `COMMON_READ_METHODS` and `READ_VERB_ALLOWLIST`/`MUTATING_VERBS` (the read-only safety net). Pure data. The default tier probes only `READ` methods. |
| `gli4py/enumerator/coverage.py` | `GLI4PY_COVERAGE: dict[tuple[str, str], str]` — `(service, method) → wrapping GLinet method name`. Hand-maintained from `glinet.py`. |
| `gli4py/enumerator/classify.py` | Pure: `classify(envelope) -> ProbeResult` using the observed codes (`-32601`→ABSENT, `-32602`→NEEDS_PARAMS, `-32000`→AUTH_ERROR, has `result`→AVAILABLE, else OTHER). |
| `gli4py/enumerator/redact.py` | Pure: `redact(value, *, enabled) -> value` — deep copy with secret-looking field values replaced by `"<redacted>"`. |
| `gli4py/enumerator/wordlist.py` | Pure data for `--dangerous`: `SERVICE_SEEDS` and `READ_METHOD_SEEDS` / `MUTATING_METHOD_SEEDS` brute-force wordlists (seeded from the research). |
| `gli4py/enumerator/probe.py` | `async enumerate_device(...) -> DeviceReport` — login, the catalog probe loop, optional `--discover-acl` (best-effort `file`/`uci` reads), optional `--dangerous` brute loop with rate-limiting; the only I/O unit. |
| `gli4py/enumerator/report.py` | Pure: `to_json(report)` / `to_markdown(report)` / `summary_lines(report)`. |
| `gli4py/enumerator/cli.py` | `main()` — argparse (`--discover-acl`, `--dangerous`, `--dangerous-full`, `--include-destructive`, `--yes`, `--unredacted`, `--rate`, `--output-dir`, host/auth flags), `.env` loading (optional), wiring, file writing, exit codes, and the `--dangerous`/`--unredacted` confirmation/warnings. Console entry point. |

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

- **Default (redacted):** captured response values are deep-copied with the value of any key matching a case-insensitive denylist replaced by `"<redacted>"`. Seed denylist (informed by the live shapes seen in §2 — VPN/TLS configs carry key material): `password`, `passwd`, `pwd`, `key`, `psk`, `secret`, `private_key`, `privatekey`, `token`, `sid`, `hash`, `nonce`, `salt`, `device_id`, `serial`, `sn`, `ca`, `cert`, `dh`, `ta`, `pem`, `csr`. As a second safety net, very long opaque strings (≥ 64 chars, base64/hex-looking) are redacted regardless of key. Redaction is best-effort; the Markdown header notes "review before committing."
- **`--unredacted`:** disables all redaction and captures raw values. The CLI prints a prominent warning that the output contains secrets and **must not be committed**, and defaults its output directory to a non-`docs/` path (caller must pass `--output-dir`); these files are not written under `docs/devices/` unless explicitly forced.
- Both modes always also record the response **schema** (keys → value types, depth-limited), which is inherently secret-free and is the primary "API exposure" signal.

## 7. Read-only safety (hard requirement for default + `--dangerous` read tier)

Two layers protect the default and `--dangerous` (read-verb) tiers: (1) only methods tagged `READ` in the catalog / matching the read-verb seeds are probed; (2) `probe.py` asserts every method to be probed matches `READ_VERB_ALLOWLIST` (e.g. starts with `get_`, or in `{check, status, list, info, dump, state}`-style) and is NOT in `MUTATING_VERBS` (`set_`, `start`, `stop`, `add`, `del`, `delete`, `enable`, `disable`, `reboot`, `update`, `apply`, `create`, `remove`, `connect`, `disconnect`, `up`, `down`, `commit`, `signal`, …). A method that fails the allowlist is refused (skipped with a logged warning), never silently probed. **Only `--dangerous-full` bypasses layer (1)** to also probe mutating verbs — and even then layer (2)'s classification is recorded so the operator sees exactly what is mutating before it runs (see §12/§13).

## 8. Output artifacts

Per device, `device_id` is a slugified `f"{model}_{firmware_version}"`, where `model` is resolved from `system get_info` as the first present of `model` → `device_type` → `board_info` → `"unknown"`, and `firmware_version` falls back to `"unknown"` if absent:
- **`docs/devices/<device_id>.json`** — `{device: {...metadata}, services: {service: {method: {status, error_code, risk, discovered_by: "catalog"|"acl"|"brute", schema, value (redacted), covered_by: <glinet method|null>}}}}`. Machine-readable and diffable across devices.
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
- `READ_VERB_ALLOWLIST` / `MUTATING_VERBS`: mutating verbs rejected by the read-tier safety net; read verbs accepted; a catalog entry tagged `READ` whose name is mutating is caught by a consistency test.
- `catalog` integrity: every catalog method is tagged with a valid `Risk`; no `READ`-tagged method matches a mutating verb.
- brute-force planning: given the wordlists and a tier, `probe.py`'s plan contains only read methods for `--dangerous` and includes mutating methods only for `--dangerous-full` (tested without hardware by inspecting the generated plan, not by calling).
- `enumerate_device`: against a mocked raw-POST layer, end-to-end assembly produces the expected `DeviceReport` (no hardware), incl. a `--dangerous` run that surfaces a brute-discovered service the catalog lacked.

The live run is manual (needs a device) and not in CI — same pattern as the existing live tests.

## 12. Aggressive discovery tiers

### `--discover-acl` (read-only, best-effort)

Attempt the ground-truth surface map by reading the rpcd ACL files over the API:
`file list /usr/share/rpcd/acl.d` → `file read` each `*.json` → parse the `read.ubus`/`write.ubus` maps; also `uci get rpcd` and try `/usr/share/gl-ngx`, `/usr/share/oui-httpd`. If permitted, this yields the exact exposed `service → [methods]` with zero brute-force. **Verified usually blocked** on gl-ngx (`-32601` for the `file` namespace), so this tier reports "ACL discovery unavailable on this gateway" and continues; it never errors the run.

### `--dangerous` / `--dangerous-full` (brute-force)

Find endpoints the catalog misses by brute-probing `(service, method)` from `wordlist.py`, classifying by the §5 rules (`-32601` = absent; anything else = present). Because the gateway collapses unknown-service and unknown-method into `-32601`, the only "hit" signal is a non-`-32601` response.

- **`--dangerous`** probes `SERVICE_SEEDS × READ_METHOD_SEEDS` — **read verbs only**. Safe-ish: the worst case is an active read like `scan` (brief wireless hiccup) — such known-active reads are excluded from the read seeds and only reachable via `--dangerous-full`.
- **`--dangerous-full`** additionally probes `MUTATING_METHOD_SEEDS` (WRITE-tagged) and active-reads. This **may cause side effects** (see §13). Requires the flag **plus** an interactive `yes` confirmation (or `--yes`), and prints the full risk warning first. DANGEROUS-tagged methods remain excluded unless `--include-destructive` is *also* passed.
- **Rate-limiting:** sequential with a configurable `--rate` delay (default 200 ms); a `--rate 0` fast mode is opt-in. Brute results are merged into the same `DeviceReport`, tagged `discovered_by: "brute"` and with their risk classification.

## 13. Risk classification & guardrails

Every catalog and wordlist method carries a `Risk` tag — `READ` (no side effects), `WRITE` (mutates config), or `DANGEROUS` (destructive/disruptive). Seeded from the research:

- **DANGEROUS (hard-excluded from every tier, including `--dangerous-full`):** `system reboot`/`reset_firmware`/`factoryreset`/`sysupgrade`/`signal`/`set_password`, `rpc-sys upgrade_start`/`factory`/`reboot`, `file write`/`remove`/`exec`, `uci commit`/`apply`, `network.interface * up/down`, `service signal`, `upgrade upgrade_online`/`upgrade_local`, `modem reboot_modem`/`send_at_command`, `ui init`, `cloud unbind`. Probing these requires a *third* explicit flag `--include-destructive` **plus** confirmation — they are never reached by `--dangerous` or `--dangerous-full` alone.
- **WRITE (config-mutating):** all `set_*`, `add_*`, `remove_*`, `start`, `connect`, `disconnect`, etc.
- **Active reads fenced out of the default read seeds:** `repeater scan`, `wifi`/`iwinfo scan`, `diag ping`/`traceroute`, `session list`, `upgrade check_firmware_online` (external call). These are reachable only via `--dangerous-full` or explicit catalog opt-in, with a note in output.

Guardrails: the default and `--dangerous` tiers are mechanically incapable of issuing a non-`READ` call (§7). `--dangerous-full` is the sole exception, gated by an explicit flag + confirmation, and every mutating call it makes is logged with its risk tag.

## 14. Open follow-ups (non-blocking)

- Grow the catalog as new devices/firmwares are enumerated (each run may reveal `-32601` gaps to fill with alternate method names).
- A future `--diff <other.json>` to compare two devices' surfaces.
- Optionally generate the catalog seed programmatically from `tomtana/python-glinet`'s `api_description.json` rather than hand-porting; hand-curated (with risk tags) for now.
- Optionally derive `GLI4PY_COVERAGE` automatically from `glinet.py` later; hand-maintained for now.
