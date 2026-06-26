# GL.iNet device API enumerator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `gli4py-enumerate` CLI that discovers a GL.iNet device's RPC service/method surface (catalog probe + auto SSH ground-truth + opt-in `--dangerous` brute-force), classifies and redacts results, annotates gli4py coverage, and writes JSON + Markdown per device.

**Architecture:** A `gli4py/enumerator/` subpackage of small pure units (catalog, classify, redact/schema, coverage, wordlist, ssh parsers, report) plus one async I/O engine (`probe.py`) and a `cli.py`. The engine takes an injectable async `caller(service, method, args) -> envelope` so it is fully unit-testable without hardware; the CLI wires the real caller (reuse `GLinet.login()` for auth, raw `aiohttp` POST for error-visible probing).

**Tech Stack:** Python ≥3.11, aiohttp (runtime), paramiko (optional `[ssh]` extra), python-dotenv (optional `[cli]` extra), stdlib `sqlite3`/`argparse`/`dataclasses`/`enum.StrEnum`, pytest + pytest-asyncio, ruff, mypy --strict, pylint, uv, hatchling.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-06-26-glinet-api-enumerator-design.md`. Catalog data source of truth: `docs/superpowers/specs/2026-06-26-glinet-api-catalog.md`.
- Python floor `>=3.11`; license `GPL-3.0-or-later`; all new code is `mypy --strict` clean, `ruff` clean, and `pylint` clean (new files are checked by `git ls-files '*.py'` and the `gli4py` mypy target).
- **Default mode is strictly read-only.** Only `READ`-tagged methods are probed except under `--dangerous-full` (WRITE/active) and `--include-destructive` (DANGEROUS). The read tiers are mechanically incapable of issuing a non-read call.
- **Redaction on by default**; `--unredacted` captures raw values and must default to a non-`docs/` output dir with a "do not commit" warning. The tool always also records secret-free schema.
- **No change to the `gli4py` library API** — the enumerator reuses `GLinet.login()` / `GLinet.sid` / `GLinetTransport.build_sid_payload(method, params, sid)` only.
- **SSH runs automatically** when it authenticates (`root` + `GLINET_PASSWORD` by default); `--no-ssh` disables; SSH failure is non-fatal (log + fall back to catalog tier). Read-only on the device.
- Console entry point `gli4py-enumerate = "gli4py.enumerator.cli:main"`. Optional extras `cli = ["python-dotenv>=1.0"]`, `ssh = ["paramiko>=3"]`. Core runtime deps unchanged (lean wheel preserved).
- Classifier codes (verified live): `result`→AVAILABLE; `-32601`→ABSENT; `-32602`→NEEDS_PARAMS; `-32000`→AUTH_ERROR; `-1`→TOKEN_ERROR; other→OTHER; transport exception→UNREACHABLE.
- Commands run via uv (`uv run pytest`, `uv run mypy gli4py`, `uv run ruff ...`). pytest `asyncio_mode = "auto"` (async tests need no marker).
- **Every new test file starts with** `# pylint: disable=missing-function-docstring,redefined-outer-name` after its docstring (and add `,protected-access` if it touches `_`-prefixed members) — pylint runs over all tracked `*.py`.

## File Structure

| File | Responsibility |
|---|---|
| `gli4py/enumerator/__init__.py` | Re-export `enumerate_device`, `DeviceReport`, `Risk`, `ProbeStatus`. |
| `gli4py/enumerator/models.py` | `Risk`/`ProbeStatus` (`StrEnum`), dataclasses `ProbeResult`, `MethodReport`, `DeviceReport`, `SshSurface`, and the `Caller` type alias. |
| `gli4py/enumerator/classify.py` | `classify(envelope) -> ProbeResult`. |
| `gli4py/enumerator/redact.py` | `redact(value, *, enabled)` and `schema_of(value, depth=4)` (pure value capture). |
| `gli4py/enumerator/catalog.py` | `CATALOG: dict[str, dict[str, Risk]]`, `COMMON_READ_METHODS`, `READ_VERBS`/`MUTATING_VERBS`, `DESTRUCTIVE_METHODS`, `is_read_method(method)`, `risk_of(verb-name)`. |
| `gli4py/enumerator/coverage.py` | `GLI4PY_COVERAGE: dict[tuple[str, str], str]`, `covered_by(service, method) -> str | None`. |
| `gli4py/enumerator/wordlist.py` | `SERVICE_SEEDS`, `READ_METHOD_SEEDS`, `MUTATING_METHOD_SEEDS`, `ACTIVE_READ_SEEDS`. |
| `gli4py/enumerator/probe.py` | `async enumerate_device(caller, *, ...) -> DeviceReport`; `make_http_caller(...)` factory; brute helper `brute_plan(...)`. |
| `gli4py/enumerator/ssh.py` | pure `parse_handlers`, `parse_validators`, `parse_account_acl`; `async ssh_discover(...) -> SshSurface` (paramiko, lazy import). |
| `gli4py/enumerator/report.py` | `to_json(report)`, `to_markdown(report)`, `summary_lines(report)`. |
| `gli4py/enumerator/cli.py` | `main()` argparse + wiring + output + warnings. |
| `pyproject.toml` | `[project.scripts]`, optional extras, extend mypy overrides with `paramiko`. |
| `tests/test_enum_*.py` | One test module per unit. |

---

### Task 1: Models + classifier

**Files:**
- Create: `gli4py/enumerator/__init__.py` (empty for now), `gli4py/enumerator/models.py`, `gli4py/enumerator/classify.py`
- Test: `tests/test_enum_classify.py`

**Interfaces:**
- Produces:
  - `class Risk(StrEnum): READ; WRITE; DANGEROUS; ACTIVE` (values `"read"`/`"write"`/`"dangerous"`/`"active"`).
  - `class ProbeStatus(StrEnum): AVAILABLE; ABSENT; NEEDS_PARAMS; AUTH_ERROR; TOKEN_ERROR; OTHER; UNREACHABLE`.
  - `@dataclass(frozen=True) class ProbeResult: status: ProbeStatus; error_code: int | None = None; message: str | None = None`.
  - `@dataclass class MethodReport: service: str; method: str; status: ProbeStatus; error_code: int | None; risk: Risk; discovered_by: str; params: list[str] | None; schema: object; value: object; covered_by: str | None`.
  - `@dataclass class DeviceReport: device: dict[str, Any]; methods: list[MethodReport]`.
  - `@dataclass class SshSurface: services: list[str]; methods: dict[str, list[str]]; params: dict[str, dict[str, list[str]]]; accounts: list[dict[str, str]]; features: list[str]; ubus: list[str]; no_auth: dict[str, list[str]]`.
  - `Caller = Callable[[str, str, dict[str, Any] | None], Awaitable[dict[str, Any]]]`.
  - `classify(envelope: dict[str, Any]) -> ProbeResult`.

- [ ] **Step 1: Write the failing classifier tests**

Create `tests/test_enum_classify.py`:

```python
"""Unit tests for the enumerator probe classifier."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.classify import classify
from gli4py.enumerator.models import ProbeStatus


def test_result_is_available():
    r = classify({"id": 0, "jsonrpc": "2.0", "result": {"k": 1}})
    assert r.status is ProbeStatus.AVAILABLE
    assert r.error_code is None


def test_method_not_found_is_absent():
    r = classify({"error": {"code": -32601, "message": "Method not found"}})
    assert r.status is ProbeStatus.ABSENT
    assert r.error_code == -32601


def test_invalid_params_is_needs_params():
    r = classify({"error": {"code": -32602, "message": "Invalid params"}})
    assert r.status is ProbeStatus.NEEDS_PARAMS


def test_auth_and_token_errors():
    assert classify({"error": {"code": -32000}}).status is ProbeStatus.AUTH_ERROR
    assert classify({"error": {"code": -1}}).status is ProbeStatus.TOKEN_ERROR


def test_other_error_keeps_code_and_message():
    r = classify({"error": {"code": -12345, "message": "weird"}})
    assert r.status is ProbeStatus.OTHER
    assert r.error_code == -12345
    assert r.message == "weird"


def test_result_present_takes_precedence_over_empty_error_key():
    assert classify({"result": []}).status is ProbeStatus.AVAILABLE
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_classify.py -v`
Expected: `ModuleNotFoundError: No module named 'gli4py.enumerator'`.

- [ ] **Step 3: Create the package, models, and classifier**

Create `gli4py/enumerator/__init__.py`:

```python
"""GL.iNet device API enumerator (catalog + SSH + brute-force discovery)."""
```

Create `gli4py/enumerator/models.py`:

```python
"""Data models for the enumerator."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Risk(StrEnum):
    """A priori risk of calling a method."""

    READ = "read"
    WRITE = "write"
    DANGEROUS = "dangerous"
    ACTIVE = "active"


class ProbeStatus(StrEnum):
    """Outcome of probing one (service, method)."""

    AVAILABLE = "available"
    ABSENT = "absent"
    NEEDS_PARAMS = "needs_params"
    AUTH_ERROR = "auth_error"
    TOKEN_ERROR = "token_error"
    OTHER = "other"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class ProbeResult:
    """Classification of a single probe envelope."""

    status: ProbeStatus
    error_code: int | None = None
    message: str | None = None


@dataclass
class MethodReport:
    """One probed (service, method) with its outcome."""

    service: str
    method: str
    status: ProbeStatus
    error_code: int | None
    risk: Risk
    discovered_by: str
    params: list[str] | None
    schema: object
    value: object
    covered_by: str | None


@dataclass
class DeviceReport:
    """Full per-device enumeration."""

    device: dict[str, Any]
    methods: list[MethodReport]


@dataclass
class SshSurface:
    """What SSH ground-truth recon found on a device."""

    services: list[str] = field(default_factory=list)
    methods: dict[str, list[str]] = field(default_factory=dict)
    params: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    accounts: list[dict[str, str]] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    ubus: list[str] = field(default_factory=list)
    no_auth: dict[str, list[str]] = field(default_factory=dict)


Caller = Callable[[str, str, "dict[str, Any] | None"], Awaitable["dict[str, Any]"]]
```

Create `gli4py/enumerator/classify.py`:

```python
"""Classify a JSON-RPC envelope into a ProbeResult."""

from typing import Any

from .models import ProbeResult, ProbeStatus

_CODE_STATUS = {
    -32601: ProbeStatus.ABSENT,
    -32602: ProbeStatus.NEEDS_PARAMS,
    -32000: ProbeStatus.AUTH_ERROR,
    -1: ProbeStatus.TOKEN_ERROR,
}


def classify(envelope: dict[str, Any]) -> ProbeResult:
    """Map a JSON-RPC response envelope to a ProbeResult."""
    if "result" in envelope:
        return ProbeResult(ProbeStatus.AVAILABLE)
    error = envelope.get("error")
    if not isinstance(error, dict):
        return ProbeResult(ProbeStatus.OTHER, message="malformed envelope")
    code = error.get("code")
    message = error.get("message")
    code_int = code if isinstance(code, int) else None
    status = _CODE_STATUS.get(code_int, ProbeStatus.OTHER) if code_int is not None else ProbeStatus.OTHER
    return ProbeResult(status, error_code=code_int, message=message)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_classify.py -v`
Expected: PASS (6 passed).

- [ ] **Step 5: Typecheck/lint and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run ruff format gli4py tests`
Expected: clean.
```bash
git add gli4py/enumerator/__init__.py gli4py/enumerator/models.py gli4py/enumerator/classify.py tests/test_enum_classify.py
git commit -m "feat(enumerator): models + JSON-RPC classifier"
```

---

### Task 2: Redaction + schema capture

**Files:**
- Create: `gli4py/enumerator/redact.py`
- Test: `tests/test_enum_redact.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `redact(value: object, *, enabled: bool = True) -> object` — deep copy; secret-keyed and long-opaque string values become `"<redacted>"`.
  - `schema_of(value: object, depth: int = 4) -> object` — shape mirror with type-name leaves; never returns raw values.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enum_redact.py`:

```python
"""Unit tests for redaction and schema capture."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.redact import redact, schema_of


def test_redacts_secret_keys():
    src = {"ssid": "Home", "key": "s3cret", "private_key": "abc", "wan_password": "p"}
    out = redact(src)
    assert out["ssid"] == "Home"
    assert out["key"] == "<redacted>"
    assert out["private_key"] == "<redacted>"
    assert out["wan_password"] == "<redacted>"  # boundary match on _password


def test_short_ambiguous_token_is_exact_match_only():
    # "ca" is a denylist token but must NOT redact "cache" / "location"
    out = redact({"ca": "CERTDATA", "cache": "ok", "location": "lounge"})
    assert out["ca"] == "<redacted>"
    assert out["cache"] == "ok"
    assert out["location"] == "lounge"


def test_long_opaque_string_redacted_regardless_of_key():
    blob = "A1b2" * 20  # 80 chars, base64-ish
    out = redact({"blob": blob, "note": "short text is fine"})
    assert out["blob"] == "<redacted>"
    assert out["note"] == "short text is fine"


def test_nested_and_lists():
    out = redact({"peers": [{"name": "p", "preshared_key": "x"}]})
    assert out["peers"][0]["name"] == "p"
    assert out["peers"][0]["preshared_key"] == "<redacted>"


def test_disabled_passthrough():
    src = {"key": "s3cret"}
    assert redact(src, enabled=False) == {"key": "s3cret"}
    assert redact(src, enabled=False) is not src  # still a copy


def test_does_not_mutate_input():
    src = {"key": "s3cret"}
    redact(src)
    assert src["key"] == "s3cret"


def test_schema_of_types_only_no_values():
    s = schema_of({"a": 1, "b": "x", "c": [{"d": True}], "e": None})
    assert s == {"a": "int", "b": "str", "c": [{"d": "bool"}], "e": "NoneType"}


def test_schema_depth_limit():
    assert schema_of({"a": {"b": {"c": 1}}}, depth=1) == {"a": "dict"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_redact.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `gli4py/enumerator/redact.py`:

```python
"""Secret redaction and schema capture for probed values."""

import re

REDACTED = "<redacted>"

# Case-insensitive tokens whose value is a secret. Short/ambiguous tokens match
# only as a whole key or on a `_`-boundary; never as a bare substring.
_SECRET_TOKENS = (
    "password", "passwd", "pwd", "key", "psk", "secret", "private_key",
    "privatekey", "token", "sid", "hash", "nonce", "salt", "device_id",
    "serial", "sn", "ca", "cert", "dh", "ta", "pem", "csr",
)
_OPAQUE = re.compile(r"^[A-Za-z0-9+/=_-]+$")


def _key_is_secret(key: str) -> bool:
    low = key.lower()
    for tok in _SECRET_TOKENS:
        if low == tok or low.endswith("_" + tok) or low.startswith(tok + "_"):
            return True
    return False


def _redact_str(value: str, key: str | None) -> str:
    if key is not None and _key_is_secret(key):
        return REDACTED
    if len(value) >= 64 and _OPAQUE.match(value):
        return REDACTED
    return value


def redact(value: object, *, enabled: bool = True, _key: str | None = None) -> object:
    """Deep-copy ``value``, replacing secret-looking string values with ``<redacted>``."""
    if isinstance(value, dict):
        return {k: redact(v, enabled=enabled, _key=k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, enabled=enabled) for v in value]
    if enabled and isinstance(value, str):
        return _redact_str(value, _key)
    return value


def schema_of(value: object, depth: int = 4) -> object:
    """Return a type-name shape mirror of ``value`` (never raw values)."""
    if isinstance(value, dict):
        if depth <= 0:
            return "dict"
        return {k: schema_of(v, depth - 1) for k, v in value.items()}
    if isinstance(value, list):
        if depth <= 0 or not value:
            return "list"
        return [schema_of(value[0], depth - 1)]
    return type(value).__name__
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_redact.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run ruff format gli4py tests`
```bash
git add gli4py/enumerator/redact.py tests/test_enum_redact.py
git commit -m "feat(enumerator): secret redaction + schema capture"
```

---

### Task 3: Catalog + coverage

**Files:**
- Create: `gli4py/enumerator/catalog.py`, `gli4py/enumerator/coverage.py`
- Test: `tests/test_enum_catalog.py`

**Interfaces:**
- Consumes: `Risk` (Task 1).
- Produces:
  - `CATALOG: dict[str, dict[str, Risk]]` — service → method → risk.
  - `COMMON_READ_METHODS: tuple[str, ...]` — read methods tried against every catalog service.
  - `READ_VERBS`, `MUTATING_VERBS`, `DESTRUCTIVE_METHODS: frozenset[str]`.
  - `is_read_method(method: str) -> bool` — True iff a read verb and not mutating.
  - `risk_of(method: str) -> Risk` — heuristic risk from the method name (used for brute hits).
  - `GLI4PY_COVERAGE: dict[tuple[str, str], str]` and `covered_by(service: str, method: str) -> str | None`.

- [ ] **Step 1: Write the failing tests (integrity + helpers)**

Create `tests/test_enum_catalog.py`:

```python
"""Catalog integrity + verb helpers + coverage."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.catalog import (
    CATALOG,
    DESTRUCTIVE_METHODS,
    MUTATING_VERBS,
    is_read_method,
    risk_of,
)
from gli4py.enumerator.coverage import covered_by
from gli4py.enumerator.models import Risk


def test_catalog_nonempty_and_well_typed():
    assert len(CATALOG) >= 30
    for service, methods in CATALOG.items():
        assert service and isinstance(methods, dict) and methods
        for method, risk in methods.items():
            assert isinstance(risk, Risk), f"{service}.{method} not a Risk"


def test_no_read_tagged_method_is_actually_mutating():
    for service, methods in CATALOG.items():
        for method, risk in methods.items():
            if risk is Risk.READ:
                assert is_read_method(method), f"{service}.{method} tagged READ but looks mutating"


def test_known_services_present():
    for s in ("system", "wifi", "clients", "firewall", "wg-server", "flow_statistics", "tor"):
        assert s in CATALOG


def test_is_read_method():
    assert is_read_method("get_config")
    assert is_read_method("check_config")
    assert not is_read_method("set_config")
    assert not is_read_method("start")
    assert not is_read_method("reboot")


def test_risk_of():
    assert risk_of("get_status") is Risk.READ
    assert risk_of("set_config") is Risk.WRITE
    assert risk_of("reboot") is Risk.DANGEROUS
    assert "reboot" in DESTRUCTIVE_METHODS
    assert "set_config" in {v for v in MUTATING_VERBS} or risk_of("set_config") is Risk.WRITE


def test_coverage_lookup():
    assert covered_by("system", "get_info") == "router_info"
    assert covered_by("clients", "get_list") == "list_all_clients"
    assert covered_by("nonexistent", "get_x") is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_catalog.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement catalog + coverage**

Create `gli4py/enumerator/catalog.py`. **Port the full `CATALOG` from `docs/superpowers/specs/2026-06-26-glinet-api-catalog.md`** (its `R`/`W`/`D`/`A` tags map to `Risk.READ`/`WRITE`/`DANGEROUS`/`ACTIVE`). The structure and ~6 representative services are shown below; port the remaining services (acl, adguardhome, bark, black_white_list, cable, cloud, ddns, dns, dpi, edgerouter, igmp, ipv6, kmwan, lan, led, logread, macclone, mcu, modem, mptun, nas_web, netmode, network, netifyd, ovpn-client, ovpn-server, parental-control, plugins, qos, repeater, rtty, s2s, samba, dlna, sms-forward, sqm, srv_conn_check, switch-button, tailscale, tethering, timer, ui, upgrade, vpn-client, vpn-policy, wg-client, zerotier) the same way, using that doc's tags:

```python
"""Curated, risk-classified GL.iNet RPC catalog (seeds the default probe).

Ported from docs/superpowers/specs/2026-06-26-glinet-api-catalog.md.
"""

from .models import Risk

R, W, D, A = Risk.READ, Risk.WRITE, Risk.DANGEROUS, Risk.ACTIVE

CATALOG: dict[str, dict[str, Risk]] = {
    "system": {
        "get_info": R, "get_status": R, "get_load": R, "disk_info": R,
        "get_timezone_config": R, "get_unixtime": R, "get_httpd_mem_status": R,
        "get_security_policy": R, "get_percent": R,
        "set_timezone_config": W, "set_security_policy": W, "add_user": W,
        "remove_user": W, "set_password": D, "reset_firmware": D, "reboot": D,
    },
    "wifi": {"get_config": R, "get_status": R, "get_mlo_config": R,
             "set_config": W, "set_txpower": W, "set_mlo_config": W},
    "clients": {"get_list": R, "get_status": R, "block_client": W,
                "remove_offline": W, "set_info": W, "clear_cache": W},
    "firewall": {"get_zone_list": R, "get_rule_list": R, "get_dmz": R,
                 "get_port_forward_list": R, "get_wan_access": R,
                 "get_acl_rule_list": R, "get_acl_zone_list": R,
                 "add_rule": W, "set_rule": W, "remove_rule": W, "set_dmz": W,
                 "add_port_forward": W, "set_port_forward": W,
                 "remove_port_forward": W, "set_wan_access": W},
    "wg-server": {"get_status": R, "get_config": R, "get_peer_list": R,
                  "get_route_list": R, "get_setting": R, "start": W, "stop": W,
                  "set_config": W, "add_peer": W, "set_peer": W, "remove_peer": W,
                  "generate_peer": W, "generate_key": W, "generate_publickey": W},
    "flow_statistics": {"get_flow_statistics": R, "get_app_flow_statistics": R,
                        "get_top_app_flow_statistics": R, "get_statistics_rule": R,
                        "set_statistics_rule": W, "clear_statistics": W},
    "tor": {"get_config": R, "get_status": R, "set_config": W, "replace_country": W},
    # ... PORT REMAINING SERVICES FROM THE CATALOG DOC (see list above) ...
}

# Read methods tried against every catalog service even if not explicitly listed.
COMMON_READ_METHODS: tuple[str, ...] = (
    "get_status", "get_config", "get_info", "get_list",
)

READ_VERBS: frozenset[str] = frozenset({"get", "list", "check", "status", "info", "dump", "state"})
MUTATING_VERBS: frozenset[str] = frozenset({
    "set", "add", "del", "delete", "remove", "start", "stop", "restart",
    "enable", "disable", "connect", "disconnect", "up", "down", "commit",
    "apply", "create", "update", "signal", "clear", "generate", "send",
    "install", "reset", "block", "init", "unbind", "export", "run",
})
DESTRUCTIVE_METHODS: frozenset[str] = frozenset({
    "reboot", "reset_firmware", "factoryreset", "sysupgrade", "factory",
    "upgrade_start", "upgrade_online", "upgrade_local", "watchdog", "signal",
    "write", "exec", "remove", "commit", "apply", "password_set", "set_password",
    "reboot_modem", "send_at_command", "init", "unbind", "generate_certificate",
})


def _first_token(method: str) -> str:
    return method.split("_", 1)[0]


def is_read_method(method: str) -> bool:
    """True iff the method name is a read verb and not a mutating one."""
    if method in DESTRUCTIVE_METHODS:
        return False
    token = _first_token(method)
    if token in MUTATING_VERBS or method in MUTATING_VERBS:
        return False
    return token in READ_VERBS


def risk_of(method: str) -> Risk:
    """Heuristic risk for a method discovered outside the catalog."""
    if method in DESTRUCTIVE_METHODS:
        return Risk.DANGEROUS
    if is_read_method(method):
        return Risk.READ
    return Risk.WRITE
```

Create `gli4py/enumerator/coverage.py` (hand-maintained from `gli4py/glinet.py` — the `(service, method)` each public method calls):

```python
"""Map RPC (service, method) pairs to the GLinet method that wraps them."""

GLI4PY_COVERAGE: dict[tuple[str, str], str] = {
    ("system", "get_info"): "router_info",
    ("system", "get_status"): "router_get_status",
    ("system", "get_load"): "router_get_load",
    ("system", "reboot"): "router_reboot",
    ("macclone", "get_mac"): "router_mac",
    ("edgerouter", "get_status"): "connected_to_internet",
    ("clients", "get_list"): "list_all_clients",
    ("lan", "get_static_bind_list"): "list_static_clients",
    ("wifi", "get_config"): "wifi_ifaces_get",
    ("wifi", "set_config"): "wifi_iface_set_enabled",
    ("diag", "ping"): "ping",
    ("wg-client", "get_all_config_list"): "wireguard_client_list",
    ("wg-client", "get_status"): "wireguard_client_state",
    ("wg-client", "start"): "wireguard_client_start",
    ("wg-client", "stop"): "wireguard_client_stop",
    ("vpn-client", "get_status"): "wireguard_client_state",
    ("vpn-client", "set_tunnel"): "wireguard_client_start",
    ("tailscale", "get_status"): "tailscale_connection_state",
    ("tailscale", "get_config"): "tailscale_configured",
    ("tailscale", "set_config"): "tailscale_start",
}


def covered_by(service: str, method: str) -> str | None:
    """Return the GLinet method wrapping (service, method), or None."""
    return GLI4PY_COVERAGE.get((service, method))
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_catalog.py -v`
Expected: PASS. The integrity tests (`test_no_read_tagged_method_is_actually_mutating`) will catch any mis-tagged port — fix tags until green.

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run pylint --disable=import-error,fixme,line-too-long,invalid-name,too-many-public-methods,abstract-method,overridden-final-method,too-many-instance-attributes,too-many-public-methods,too-few-public-methods,too-many-branches gli4py/enumerator/catalog.py gli4py/enumerator/coverage.py`
Expected: clean / `10.00`.
```bash
git add gli4py/enumerator/catalog.py gli4py/enumerator/coverage.py tests/test_enum_catalog.py
git commit -m "feat(enumerator): risk-classified catalog + gli4py coverage map"
```

---

### Task 4: Enumeration engine (catalog tier)

**Files:**
- Create: `gli4py/enumerator/probe.py`
- Test: `tests/test_enum_probe.py`

**Interfaces:**
- Consumes: `Caller`, `MethodReport`, `DeviceReport`, `ProbeStatus`, `Risk` (Task 1); `classify` (Task 1); `redact`, `schema_of` (Task 2); `CATALOG`, `COMMON_READ_METHODS`, `is_read_method`, `risk_of`, `covered_by` (Task 3).
- Produces:
  - `async enumerate_device(caller: Caller, *, redact_values: bool = True, device_info: dict[str, Any] | None = None) -> DeviceReport` — probes catalog READ methods + `COMMON_READ_METHODS`, returns a `DeviceReport`. `device_info` is the parsed `system get_info` (caller fetches it if None).
  - `def device_id(device: dict[str, Any]) -> str` — slug `f"{model}_{firmware}"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enum_probe.py`:

```python
"""Engine tests against a fake caller (no hardware)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.models import ProbeStatus
from gli4py.enumerator.probe import device_id, enumerate_device


def make_caller(responses):
    async def caller(service, method, args):  # noqa: ARG001
        return responses.get((service, method), {"error": {"code": -32601, "message": "Method not found"}})
    return caller


async def test_enumerate_marks_available_absent_and_redacts():
    responses = {
        ("system", "get_info"): {"result": {"model": "mt6000", "firmware_version": "4.8.0"}},
        ("wg-server", "get_config"): {"result": {"port": 51820, "private_key": "SECRET"}},
    }
    report = await enumerate_device(make_caller(responses), device_info={"model": "mt6000", "firmware_version": "4.8.0"})
    by = {(m.service, m.method): m for m in report.methods}
    assert by[("wg-server", "get_config")].status is ProbeStatus.AVAILABLE
    assert by[("wg-server", "get_config")].value == {"port": 51820, "private_key": "<redacted>"}
    assert by[("wg-server", "get_config")].schema == {"port": "int", "private_key": "str"}
    # an unanswered catalog method classifies ABSENT
    assert by[("system", "reboot")].status is ProbeStatus.ABSENT if ("system", "reboot") in by else True


async def test_only_read_methods_are_probed():
    seen = []

    async def caller(service, method, args):  # noqa: ARG001
        seen.append((service, method))
        return {"result": {}}

    await enumerate_device(caller, device_info={"model": "x", "firmware_version": "1"})
    assert seen, "should have probed something"
    from gli4py.enumerator.catalog import is_read_method  # local import keeps the test focused
    assert all(is_read_method(m) for _, m in seen)


async def test_coverage_annotation():
    responses = {("system", "get_info"): {"result": {"model": "x", "firmware_version": "1"}}}
    report = await enumerate_device(make_caller(responses), device_info={"model": "x", "firmware_version": "1"})
    info = next(m for m in report.methods if (m.service, m.method) == ("system", "get_info"))
    assert info.covered_by == "router_info"


def test_device_id_slug():
    assert device_id({"model": "GL-MT6000", "firmware_version": "4.8.0"}) == "gl-mt6000_4.8.0"
    assert device_id({"device_type": "mt6000"}) == "mt6000_unknown"
    assert device_id({}) == "unknown_unknown"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_probe.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the engine (catalog tier)**

Create `gli4py/enumerator/probe.py`:

```python
"""Async enumeration engine: probe a device through an injectable caller."""

import re
from typing import Any

from .catalog import CATALOG, COMMON_READ_METHODS, is_read_method, risk_of
from .classify import classify
from .coverage import covered_by
from .models import Caller, DeviceReport, MethodReport, ProbeStatus, Risk
from .redact import redact, schema_of

_SLUG = re.compile(r"[^a-z0-9.]+")


def device_id(device: dict[str, Any]) -> str:
    """Slug `model_firmware` from a get_info dict, with fallbacks."""
    model = device.get("model") or device.get("device_type") or device.get("board_info") or "unknown"
    firmware = device.get("firmware_version") or "unknown"
    slug = _SLUG.sub("-", f"{model}_{firmware}".lower()).strip("-")
    return slug.replace("-_", "_").replace("_-", "_")


async def _probe(caller: Caller, service: str, method: str) -> tuple[ProbeStatus, int | None, object]:
    try:
        envelope = await caller(service, method, None)
    except Exception as exc:  # pylint: disable=broad-except
        return ProbeStatus.UNREACHABLE, None, {"error": f"{type(exc).__name__}: {exc}"}
    result = classify(envelope)
    value = envelope.get("result") if result.status is ProbeStatus.AVAILABLE else None
    return result.status, result.error_code, value


def _catalog_targets() -> list[tuple[str, str, Risk]]:
    targets: list[tuple[str, str, Risk]] = []
    seen: set[tuple[str, str]] = set()
    for service, methods in CATALOG.items():
        for method, risk in methods.items():
            if risk is Risk.READ and (service, method) not in seen:
                targets.append((service, method, risk))
                seen.add((service, method))
        for method in COMMON_READ_METHODS:
            if (service, method) not in seen:
                targets.append((service, method, Risk.READ))
                seen.add((service, method))
    return targets


async def enumerate_device(
    caller: Caller,
    *,
    redact_values: bool = True,
    device_info: dict[str, Any] | None = None,
) -> DeviceReport:
    """Probe the read-only catalog surface and assemble a DeviceReport."""
    if device_info is None:
        status, _code, value = await _probe(caller, "system", "get_info")
        device_info = value if status is ProbeStatus.AVAILABLE and isinstance(value, dict) else {}

    methods: list[MethodReport] = []
    for service, method, risk in _catalog_targets():
        assert is_read_method(method), f"refusing non-read method {service}.{method}"
        status, code, value = await _probe(caller, service, method)
        methods.append(
            MethodReport(
                service=service,
                method=method,
                status=status,
                error_code=code,
                risk=risk_of(method) if risk is None else risk,
                discovered_by="catalog",
                params=None,
                schema=schema_of(value) if value is not None else None,
                value=redact(value, enabled=redact_values) if value is not None else None,
                covered_by=covered_by(service, method),
            )
        )
    return DeviceReport(device=device_info, methods=methods)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_probe.py -v`
Expected: PASS.

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run pytest -q`
```bash
git add gli4py/enumerator/probe.py tests/test_enum_probe.py
git commit -m "feat(enumerator): catalog-tier enumeration engine"
```

---

### Task 5: Report renderers

**Files:**
- Create: `gli4py/enumerator/report.py`
- Test: `tests/test_enum_report.py`

**Interfaces:**
- Consumes: `DeviceReport`, `MethodReport`, `ProbeStatus`, `Risk`, `device_id` (Tasks 1, 4).
- Produces:
  - `to_json(report: DeviceReport) -> str` — pretty JSON; nested `services` map keyed by service then method.
  - `to_markdown(report: DeviceReport) -> str` — header + per-service table + "Available but not yet wrapped by gli4py" section.
  - `summary_lines(report: DeviceReport) -> list[str]` — counts + not-yet-wrapped list.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enum_report.py`:

```python
"""Report renderer tests."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import json

from gli4py.enumerator.models import DeviceReport, MethodReport, ProbeStatus, Risk
from gli4py.enumerator.report import summary_lines, to_json, to_markdown


def _report():
    return DeviceReport(
        device={"model": "GL-MT6000", "firmware_version": "4.8.0"},
        methods=[
            MethodReport("system", "get_info", ProbeStatus.AVAILABLE, None, Risk.READ,
                         "catalog", None, {"model": "str"}, {"model": "GL-MT6000"}, "router_info"),
            MethodReport("firewall", "get_rule_list", ProbeStatus.AVAILABLE, None, Risk.READ,
                         "catalog", None, {"res": "list"}, {"res": []}, None),
            MethodReport("modem", "get_info", ProbeStatus.ABSENT, -32601, Risk.READ,
                         "catalog", None, None, None, None),
        ],
    )


def test_to_json_round_trips_and_nests_by_service():
    data = json.loads(to_json(_report()))
    assert data["device"]["model"] == "GL-MT6000"
    assert data["services"]["firewall"]["get_rule_list"]["status"] == "available"
    assert data["services"]["system"]["get_info"]["covered_by"] == "router_info"


def test_markdown_has_header_and_not_wrapped_section():
    md = to_markdown(_report())
    assert "GL-MT6000" in md
    assert "not yet wrapped" in md.lower()
    assert "firewall" in md and "get_rule_list" in md  # available + uncovered -> listed


def test_summary_counts():
    lines = summary_lines(_report())
    text = "\n".join(lines)
    assert "available" in text.lower()
    assert "firewall.get_rule_list" in text  # the uncovered available one
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_report.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `gli4py/enumerator/report.py`:

```python
"""Render a DeviceReport to JSON, Markdown, and terminal summary."""

import json
from typing import Any

from .models import DeviceReport, MethodReport, ProbeStatus
from .probe import device_id

_PRESENT = (ProbeStatus.AVAILABLE, ProbeStatus.NEEDS_PARAMS)


def _method_dict(m: MethodReport) -> dict[str, Any]:
    return {
        "status": str(m.status),
        "error_code": m.error_code,
        "risk": str(m.risk),
        "discovered_by": m.discovered_by,
        "params": m.params,
        "schema": m.schema,
        "value": m.value,
        "covered_by": m.covered_by,
    }


def _services_map(report: DeviceReport) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for m in report.methods:
        out.setdefault(m.service, {})[m.method] = _method_dict(m)
    return out


def _not_wrapped(report: DeviceReport) -> list[MethodReport]:
    return [m for m in report.methods if m.status in _PRESENT and m.covered_by is None]


def to_json(report: DeviceReport) -> str:
    """Machine-readable per-device report."""
    return json.dumps(
        {"device": report.device, "services": _services_map(report)},
        indent=2,
        sort_keys=True,
    )


def to_markdown(report: DeviceReport) -> str:
    """Human-readable per-device API exposure document."""
    dev = report.device
    lines = [
        f"# API exposure: {dev.get('model', 'unknown')} ({dev.get('firmware_version', 'unknown')})",
        "",
        "> Values are redacted by default; review before committing.",
        "",
        "## Services",
        "",
        "| Service | Method | Status | Risk | Wrapped by gli4py |",
        "|---|---|---|---|---|",
    ]
    for m in sorted(report.methods, key=lambda x: (x.service, x.method)):
        if m.status in _PRESENT:
            lines.append(f"| {m.service} | {m.method} | {m.status} | {m.risk} | {m.covered_by or '—'} |")
    lines += ["", "## Available but not yet wrapped by gli4py", ""]
    nw = _not_wrapped(report)
    lines += [f"- `{m.service}.{m.method}`" for m in sorted(nw, key=lambda x: (x.service, x.method))] or ["- (none)"]
    return "\n".join(lines) + "\n"


def summary_lines(report: DeviceReport) -> list[str]:
    """Terminal summary: counts + the not-yet-wrapped worklist."""
    counts: dict[str, int] = {}
    for m in report.methods:
        counts[str(m.status)] = counts.get(str(m.status), 0) + 1
    nw = _not_wrapped(report)
    lines = [
        f"Device: {report.device.get('model', 'unknown')} ({report.device.get('firmware_version', 'unknown')}) "
        f"[id: {device_id(report.device)}]",
        "Counts: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())),
        f"Not yet wrapped by gli4py ({len(nw)}):",
    ]
    lines += [f"  - {m.service}.{m.method}" for m in sorted(nw, key=lambda x: (x.service, x.method))]
    return lines
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_report.py -v`
Expected: PASS.

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run pytest -q`
```bash
git add gli4py/enumerator/report.py tests/test_enum_report.py
git commit -m "feat(enumerator): JSON/Markdown/summary renderers"
```

---

### Task 6: Wordlist + `--dangerous` brute-force

**Files:**
- Create: `gli4py/enumerator/wordlist.py`
- Modify: `gli4py/enumerator/probe.py` (add `brute_plan` + brute pass in `enumerate_device`)
- Test: `tests/test_enum_brute.py`

**Interfaces:**
- Consumes: `CATALOG`, `risk_of`, `is_read_method`, `DESTRUCTIVE_METHODS` (Task 3); engine (Task 4).
- Produces:
  - `wordlist.SERVICE_SEEDS: tuple[str, ...]`, `READ_METHOD_SEEDS`, `ACTIVE_READ_SEEDS`, `MUTATING_METHOD_SEEDS`.
  - `probe.brute_plan(*, dangerous: bool, dangerous_full: bool, include_destructive: bool) -> list[tuple[str, str]]` — the `(service, method)` pairs the brute pass would try (pure; no I/O). Read-only unless `dangerous_full`; destructive only if `include_destructive`.
  - `enumerate_device(..., brute: str = "off")` extended: `brute` in `{"off", "dangerous", "dangerous_full"}` (+ `include_destructive: bool = False`), adding `discovered_by="brute"` MethodReports for non-catalog hits.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enum_brute.py`:

```python
"""Brute-force planning + a fake-caller brute run."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.catalog import DESTRUCTIVE_METHODS, is_read_method
from gli4py.enumerator.models import ProbeStatus
from gli4py.enumerator.probe import brute_plan, enumerate_device


def test_dangerous_plan_is_read_only():
    plan = brute_plan(dangerous=True, dangerous_full=False, include_destructive=False)
    assert plan
    assert all(is_read_method(method) for _, method in plan)


def test_full_plan_includes_mutating_but_not_destructive():
    plan = brute_plan(dangerous=True, dangerous_full=True, include_destructive=False)
    methods = {m for _, m in plan}
    assert any(not is_read_method(m) for m in methods)  # has mutating
    assert methods.isdisjoint(DESTRUCTIVE_METHODS)      # no destructive


def test_include_destructive_adds_destructive():
    plan = brute_plan(dangerous=True, dangerous_full=True, include_destructive=True)
    methods = {m for _, m in plan}
    assert methods & DESTRUCTIVE_METHODS


async def test_brute_surfaces_non_catalog_service():
    responses = {
        ("system", "get_info"): {"result": {"model": "x", "firmware_version": "1"}},
        ("astrowarp", "get_status"): {"result": {"on": True}},
    }

    async def caller(service, method, args):  # noqa: ARG001
        return responses.get((service, method), {"error": {"code": -32601}})

    report = await enumerate_device(
        caller, device_info={"model": "x", "firmware_version": "1"},
        brute="dangerous",
    )
    hit = next((m for m in report.methods if m.service == "astrowarp"), None)
    assert hit is not None
    assert hit.discovered_by == "brute"
    assert hit.status is ProbeStatus.AVAILABLE
```

(Ensure `astrowarp` is in `SERVICE_SEEDS` and `get_status` in `READ_METHOD_SEEDS`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_brute.py -v`
Expected: `ImportError: cannot import name 'brute_plan'` / `wordlist` missing.

- [ ] **Step 3: Implement wordlist + brute**

Create `gli4py/enumerator/wordlist.py` (seed from the catalog doc's "`--dangerous` wordlist seeds"; include `astrowarp` in services):

```python
"""Brute-force wordlists for the --dangerous tiers (seeded from research)."""

SERVICE_SEEDS: tuple[str, ...] = (
    "system", "clients", "lan", "wifi", "macclone", "diag", "edgerouter",
    "wg-client", "wg_client", "wg-server", "vpn-client", "ovpn-client",
    "ovpn-server", "tailscale", "zerotier", "tor", "repeater", "modem", "dns",
    "custom_dns", "ddns", "adguardhome", "firewall", "vpn-policy", "ipv6",
    "network", "upgrade", "logread", "led", "netmode", "s2s", "cloud", "rtty",
    "fan", "cable", "switch-button", "igmp", "qos", "acl", "rs485", "samba",
    "nas_web", "dlna", "plugins", "tethering", "reboot", "kmwan", "bark",
    "parental-control", "black_white_list", "mcu", "dpi", "flow_statistics",
    "sqm", "mptun", "sms-forward", "local-access", "srv_conn_check", "timer",
    "netifyd", "astrowarp", "sdwan", "vlan", "bridge", "ipsec", "dpifeatures",
)
READ_METHOD_SEEDS: tuple[str, ...] = (
    "get_status", "get_config", "get_info", "get_list", "get_all_config_list",
    "get_config_list", "get_group_list", "get_route_list", "get_setting",
    "get_mac", "get_mode", "get_ipv6", "get_host", "get_zone_list",
    "get_rule_list", "get_port_forward_list", "get_peer_list", "get_user_list",
    "get_repository_status", "get_lang", "get_menu_list", "check_initialized",
    "status", "info", "list", "dump", "state", "check_config", "get_data",
)
ACTIVE_READ_SEEDS: tuple[str, ...] = (
    "scan", "get_scan_list", "get_saved_ap_list", "check_firmware_online",
)
MUTATING_METHOD_SEEDS: tuple[str, ...] = (
    "set_config", "set_status", "set_tunnel", "start", "stop", "restart",
    "enable", "disable", "connect", "disconnect", "add_config", "remove_config",
    "set_proxy", "set_setting", "block_client", "set_mac", "set_mode",
    "upgrade_online", "upgrade_local", "reboot", "reset_firmware", "factoryreset",
)
```

Modify `gli4py/enumerator/probe.py` — add imports and the brute plan + pass:

```python
# add to imports
from .catalog import DESTRUCTIVE_METHODS
from .wordlist import (
    ACTIVE_READ_SEEDS,
    MUTATING_METHOD_SEEDS,
    READ_METHOD_SEEDS,
    SERVICE_SEEDS,
)


def brute_plan(*, dangerous: bool, dangerous_full: bool, include_destructive: bool) -> list[tuple[str, str]]:
    """The (service, method) pairs the brute pass will try."""
    if not dangerous:
        return []
    methods: list[str] = [m for m in READ_METHOD_SEEDS]
    if dangerous_full:
        methods += list(ACTIVE_READ_SEEDS) + list(MUTATING_METHOD_SEEDS)
    methods = [m for m in methods if include_destructive or m not in DESTRUCTIVE_METHODS]
    seen: set[tuple[str, str]] = set()
    plan: list[tuple[str, str]] = []
    for service in SERVICE_SEEDS:
        for method in methods:
            if (service, method) not in seen:
                seen.add((service, method))
                plan.append((service, method))
    return plan
```

Extend `enumerate_device`'s signature and add the brute pass after the catalog loop (before `return`):

```python
async def enumerate_device(
    caller: Caller,
    *,
    redact_values: bool = True,
    device_info: dict[str, Any] | None = None,
    brute: str = "off",
    include_destructive: bool = False,
) -> DeviceReport:
    ...  # existing get_info + catalog loop, building `methods`
    probed = {(m.service, m.method) for m in methods}
    if brute != "off":
        plan = brute_plan(
            dangerous=True,
            dangerous_full=(brute == "dangerous_full"),
            include_destructive=include_destructive,
        )
        for service, method in plan:
            if (service, method) in probed:
                continue
            status, code, value = await _probe(caller, service, method)
            if status is ProbeStatus.ABSENT:
                continue  # only record hits
            methods.append(
                MethodReport(
                    service=service, method=method, status=status, error_code=code,
                    risk=risk_of(method), discovered_by="brute", params=None,
                    schema=schema_of(value) if value is not None else None,
                    value=redact(value, enabled=redact_values) if value is not None else None,
                    covered_by=covered_by(service, method),
                )
            )
    return DeviceReport(device=device_info, methods=methods)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_brute.py tests/test_enum_probe.py -v`
Expected: PASS (brute tests + existing engine tests still green).

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run pytest -q`
```bash
git add gli4py/enumerator/wordlist.py gli4py/enumerator/probe.py tests/test_enum_brute.py
git commit -m "feat(enumerator): --dangerous brute-force discovery + wordlists"
```

---

### Task 7: SSH parsers (pure)

**Files:**
- Create: `gli4py/enumerator/ssh.py` (pure parsers only this task)
- Test: `tests/test_enum_ssh_parse.py`

**Interfaces:**
- Consumes: `SshSurface` (Task 1).
- Produces:
  - `parse_handlers(listing: list[str], sources: dict[str, str]) -> dict[str, list[str]]` — service → method candidates. `listing` is the `ls` of the handler dir; `sources[name]` is the Lua text or `strings` dump for handler `name`. Normalizes `.so`/underscore/hyphen duplicates.
  - `parse_validators(sources: dict[str, str]) -> dict[str, dict[str, list[str]]]` — service → `{method: [params]}` from `gl-validator.d` files.
  - `parse_account_acl(rows: list[tuple[str, str]]) -> tuple[list[dict[str, str]], bool]` — accounts list + `root_has_full` flag.

- [ ] **Step 1: Write the failing tests (fixtures captured from the live recon)**

Create `tests/test_enum_ssh_parse.py`:

```python
"""Pure SSH-parser tests (fixtures from live recon)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.ssh import parse_account_acl, parse_handlers, parse_validators

LUA_TOR = """
local M = {}
function M.get_config() end
function M.set_config() end
function M.get_status() end
return M
"""

# `strings` dump from a .so (real method names + internal-helper noise)
SO_WG = "\n".join([
    "get_all_config_list", "add_config", "set_config", "set_proxy",
    "check_string_length", "get_peer_key", "xyzzy_internal",
])


def test_parse_handlers_lua_and_so_with_dedup():
    listing = ["tor", "wg-client.so", "wg_client"]
    sources = {"tor": LUA_TOR, "wg-client.so": SO_WG, "wg_client": ""}
    out = parse_handlers(listing, sources)
    assert out["tor"] == sorted(["get_config", "set_config", "get_status"])
    # .so/underscore collapse to the hyphenated service
    assert "wg-client" in out
    assert "wg_client" not in out and "wg-client.so" not in out
    assert "get_all_config_list" in out["wg-client"]
    assert "set_config" in out["wg-client"]
    # obvious noise filtered (not a known verb prefix)
    assert "xyzzy_internal" not in out["wg-client"]


def test_parse_validators_extracts_methods_and_params():
    validators = {
        "tor": 'local M = { ["set_config"] = { "enable", "manual" }, ["get_config"] = {} }\nreturn M',
    }
    out = parse_validators(validators)
    assert "set_config" in out["tor"]
    assert out["tor"]["set_config"] == ["enable", "manual"]


def test_parse_account_acl_root_full():
    accounts, root_full = parse_account_acl([("root", "root"), ("guest", "limited")])
    assert {"username": "root", "acl": "root"} in accounts
    assert root_full is True
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_ssh_parse.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the pure parsers**

Create `gli4py/enumerator/ssh.py`:

```python
"""SSH ground-truth discovery: pure parsers + (later) paramiko I/O."""

import re

from .catalog import is_read_method
from .models import SshSurface  # noqa: F401  (used by ssh_discover in Task 8)

_LUA_FUNC = re.compile(r"function\s+M\.([A-Za-z0-9_]+)")
_LUA_ASSIGN = re.compile(r'M\.([A-Za-z0-9_]+)\s*=\s*function')
_LUA_KEY = re.compile(r'\[\s*["\']([A-Za-z0-9_]+)["\']\s*\]')
_VERB_PREFIXES = ("get_", "set_", "add_", "remove_", "del_", "list_", "check_",
                  "start", "stop", "generate_", "export_", "clear_", "connect",
                  "disconnect", "scan", "status", "info", "dump")
_VALIDATOR_ENTRY = re.compile(r'\[\s*["\']([A-Za-z0-9_]+)["\']\s*\]\s*=\s*\{([^}]*)\}')
_PARAM = re.compile(r'["\']([A-Za-z0-9_]+)["\']')


def _canonical_service(name: str) -> str:
    base = name[:-3] if name.endswith(".so") else name
    return base.replace("_", "-")


def _looks_like_method(token: str) -> bool:
    return any(token.startswith(p) for p in _VERB_PREFIXES)


def parse_handlers(listing: list[str], sources: dict[str, str]) -> dict[str, list[str]]:
    """Extract service -> method candidates from handler dir + source/strings."""
    out: dict[str, set[str]] = {}
    for name in listing:
        if name.endswith(".lua"):
            continue
        service = _canonical_service(name)
        text = sources.get(name, "")
        methods = set(_LUA_FUNC.findall(text)) | set(_LUA_ASSIGN.findall(text))
        if not methods:  # .so / bytecode strings dump
            methods = {t for t in text.split() if _looks_like_method(t)}
        out.setdefault(service, set()).update(methods)
    return {s: sorted(m) for s, m in out.items() if m}


def parse_validators(sources: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    """Extract service -> {method: [params]} from gl-validator.d files."""
    out: dict[str, dict[str, list[str]]] = {}
    for service, text in sources.items():
        methods: dict[str, list[str]] = {}
        for method, body in _VALIDATOR_ENTRY.findall(text):
            methods[method] = _PARAM.findall(body)
        if methods:
            out[service.replace("_", "-")] = methods
    return out


def parse_account_acl(rows: list[tuple[str, str]]) -> tuple[list[dict[str, str]], bool]:
    """Accounts + whether a root-acl account exists (=> full access)."""
    accounts = [{"username": u, "acl": a} for u, a in rows]
    root_full = any(a == "root" for _u, a in rows)
    return accounts, root_full


__all__ = ["parse_handlers", "parse_validators", "parse_account_acl", "is_read_method"]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_ssh_parse.py -v`
Expected: PASS.

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run pytest -q`
```bash
git add gli4py/enumerator/ssh.py tests/test_enum_ssh_parse.py
git commit -m "feat(enumerator): pure SSH handler/validator/acl parsers"
```

---

### Task 8: SSH discovery (paramiko) + engine integration

**Files:**
- Modify: `gli4py/enumerator/ssh.py` (add `ssh_discover`), `gli4py/enumerator/probe.py` (merge `ssh_surface` into `enumerate_device`)
- Test: `tests/test_enum_ssh_integration.py`

**Interfaces:**
- Consumes: parsers (Task 7); engine (Tasks 4, 6).
- Produces:
  - `async ssh_discover(host: str, *, username: str = "root", password: str | None = None, key_filename: str | None = None, port: int = 22, timeout: float = 12.0) -> SshSurface` — paramiko (lazy import); raises `SshUnavailable` on connect/auth failure or if paramiko is missing.
  - `class SshUnavailable(RuntimeError)`.
  - `enumerate_device(..., ssh_surface: SshSurface | None = None)` — for each SSH-discovered `(service, method)` not already probed, probe it read-only (or, if not a read method, record without calling) and tag `discovered_by="ssh"`, attaching `params` from validators when present; add `device["accounts"]`/`device["features"]`.

- [ ] **Step 1: Write the failing integration test (no paramiko/hardware)**

Create `tests/test_enum_ssh_integration.py`:

```python
"""enumerate_device merges an injected SshSurface (no paramiko needed)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

from gli4py.enumerator.models import ProbeStatus, SshSurface
from gli4py.enumerator.probe import enumerate_device


async def test_ssh_surface_adds_confirmed_methods_with_params():
    responses = {
        ("system", "get_info"): {"result": {"model": "x", "firmware_version": "1"}},
        ("flow_statistics", "get_flow_statistics"): {"result": {"rx": 1, "tx": 2}},
    }

    async def caller(service, method, args):  # noqa: ARG001
        return responses.get((service, method), {"error": {"code": -32601}})

    surface = SshSurface(
        services=["flow_statistics"],
        methods={"flow_statistics": ["get_flow_statistics"]},
        params={"flow_statistics": {"get_flow_statistics": ["period"]}},
        accounts=[{"username": "root", "acl": "root"}],
        features=["flowstatistics"],
    )
    report = await enumerate_device(
        caller, device_info={"model": "x", "firmware_version": "1"}, ssh_surface=surface,
    )
    hit = next(m for m in report.methods if (m.service, m.method) == ("flow_statistics", "get_flow_statistics"))
    assert hit.discovered_by == "ssh"
    assert hit.status is ProbeStatus.AVAILABLE
    assert hit.params == ["period"]
    assert report.device["accounts"] == [{"username": "root", "acl": "root"}]
    assert report.device["features"] == ["flowstatistics"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_ssh_integration.py -v`
Expected: FAIL — `enumerate_device()` got an unexpected keyword `ssh_surface`.

- [ ] **Step 3: Implement `ssh_discover` + merge**

Append to `gli4py/enumerator/ssh.py`:

```python
import asyncio
from typing import Any

REMOTE_RECON = r"""
echo '@@HANDLERS@@'; ls -1 /usr/lib/oui-httpd/rpc/ 2>/dev/null
echo '@@UBUS@@'; ubus list 2>/dev/null
echo '@@ACCOUNTS@@'; sqlite3 /etc/oui/oui.db 'SELECT username||"|"||acl FROM account;' 2>/dev/null
echo '@@FEATURES@@'; ls -1 /usr/share/oui/menu.d/ 2>/dev/null | sed 's/.json$//'
echo '@@END@@'
"""


class SshUnavailable(RuntimeError):
    """SSH could not be used (unreachable, auth failed, or paramiko missing)."""


def _section(blob: str, tag: str) -> list[str]:
    body = blob.split(f"@@{tag}@@", 1)
    if len(body) < 2:
        return []
    rest = body[1]
    rest = re.split(r"@@[A-Z]+@@", rest, 1)[0]
    return [ln.strip() for ln in rest.splitlines() if ln.strip()]


async def ssh_discover(
    host: str,
    *,
    username: str = "root",
    password: str | None = None,
    key_filename: str | None = None,
    port: int = 22,
    timeout: float = 12.0,
) -> SshSurface:
    """Read-only SSH recon -> SshSurface. Raises SshUnavailable on failure."""
    try:
        import paramiko  # noqa: PLC0415  (optional dependency, lazy)
    except ImportError as exc:  # pragma: no cover - exercised via integration env
        raise SshUnavailable("paramiko not installed (pip install 'gli4py[ssh]')") from exc

    def _run() -> tuple[str, dict[str, str], dict[str, str]]:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                host, port=port, username=username, password=password,
                key_filename=key_filename, timeout=timeout,
                look_for_keys=bool(key_filename), allow_agent=False,
            )
        except Exception as exc:  # pylint: disable=broad-except
            raise SshUnavailable(f"SSH connect failed: {type(exc).__name__}: {exc}") from exc
        try:
            _in, out, _err = client.exec_command(REMOTE_RECON, timeout=timeout)
            recon = out.read().decode(errors="replace")
            handler_names = _section(recon, "HANDLERS")
            handler_sources: dict[str, str] = {}
            for name in handler_names:
                cmd = f"if grep -q 'function M\\.' /usr/lib/oui-httpd/rpc/{name} 2>/dev/null; then cat /usr/lib/oui-httpd/rpc/{name}; else strings /usr/lib/oui-httpd/rpc/{name} 2>/dev/null; fi"
                _i, o, _e = client.exec_command(cmd, timeout=timeout)
                handler_sources[name] = o.read().decode(errors="replace")
            validator_sources: dict[str, str] = {}
            _i, vo, _e = client.exec_command("ls -1 /usr/share/gl-validator.d/ 2>/dev/null", timeout=timeout)
            for vf in [x.strip() for x in vo.read().decode(errors="replace").splitlines() if x.strip()]:
                _i2, vc, _e2 = client.exec_command(f"cat /usr/share/gl-validator.d/{vf}", timeout=timeout)
                validator_sources[vf[:-4] if vf.endswith(".lua") else vf] = vc.read().decode(errors="replace")
            return recon, handler_sources, validator_sources
        finally:
            client.close()

    recon, handler_sources, validator_sources = await asyncio.to_thread(_run)

    handlers = parse_handlers(_section(recon, "HANDLERS"), handler_sources)
    validators = parse_validators(validator_sources)
    for service, methods in validators.items():
        handlers.setdefault(service, [])
        handlers[service] = sorted(set(handlers[service]) | set(methods))
    accounts, _root_full = parse_account_acl(
        [tuple(row.split("|", 1)) for row in _section(recon, "ACCOUNTS") if "|" in row]  # type: ignore[misc]
    )
    return SshSurface(
        services=sorted(handlers),
        methods=handlers,
        params=validators,
        accounts=accounts,
        features=_section(recon, "FEATURES"),
        ubus=_section(recon, "UBUS"),
    )
```

Update `gli4py/enumerator/probe.py` `enumerate_device` to accept and merge `ssh_surface`:

```python
from .models import SshSurface  # add to imports

async def enumerate_device(
    caller: Caller,
    *,
    redact_values: bool = True,
    device_info: dict[str, Any] | None = None,
    brute: str = "off",
    include_destructive: bool = False,
    ssh_surface: SshSurface | None = None,
) -> DeviceReport:
    ...  # get_info + catalog loop + brute loop, building `methods`
    probed = {(m.service, m.method) for m in methods}
    if ssh_surface is not None:
        for service, smethods in ssh_surface.methods.items():
            params_map = ssh_surface.params.get(service, {})
            for method in smethods:
                if (service, method) in probed:
                    continue
                probed.add((service, method))
                if is_read_method(method):
                    status, code, value = await _probe(caller, service, method)
                else:
                    status, code, value = ProbeStatus.OTHER, None, None  # don't call non-reads
                methods.append(
                    MethodReport(
                        service=service, method=method, status=status, error_code=code,
                        risk=risk_of(method), discovered_by="ssh",
                        params=params_map.get(method),
                        schema=schema_of(value) if value is not None else None,
                        value=redact(value, enabled=redact_values) if value is not None else None,
                        covered_by=covered_by(service, method),
                    )
                )
        device_info = {**(device_info or {}), "accounts": ssh_surface.accounts, "features": ssh_surface.features}
    return DeviceReport(device=device_info or {}, methods=methods)
```

> Place the `ssh_surface` merge **before** the final `return`, and remove the earlier `return DeviceReport(...)` added in Task 6 so there is a single return. The `device_info` is guaranteed non-None by the get_info step at the top.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_ssh_integration.py tests/test_enum_probe.py tests/test_enum_brute.py -v`
Expected: PASS (merge works; earlier engine/brute tests still green).

- [ ] **Step 5: Lint/type and commit**

Run: `uv run mypy gli4py && uv run ruff check . && uv run pytest -q`
Expected: clean. (`paramiko` import is inside the function; mypy override added in Task 9 — if mypy flags the missing stub now, proceed; Task 9 silences it.)
```bash
git add gli4py/enumerator/ssh.py gli4py/enumerator/probe.py tests/test_enum_ssh_integration.py
git commit -m "feat(enumerator): SSH ground-truth discovery + engine merge"
```

---

### Task 9: CLI + packaging

**Files:**
- Modify: `gli4py/enumerator/__init__.py`, `pyproject.toml`
- Create: `gli4py/enumerator/cli.py`
- Test: `tests/test_enum_cli.py`

**Interfaces:**
- Consumes: everything.
- Produces:
  - `cli.build_parser() -> argparse.ArgumentParser`.
  - `cli.resolve_brute(args) -> tuple[str, bool]` — `(brute_mode, include_destructive)` from flags.
  - `cli.output_dir_for(args, *, redacted: bool) -> str` — `docs/devices` when redacted, else requires `--output-dir`.
  - `cli.main(argv: list[str] | None = None) -> int`.
  - `gli4py.enumerator.__init__` re-exports `enumerate_device`, `DeviceReport`, `Risk`, `ProbeStatus`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_enum_cli.py`:

```python
"""CLI argument wiring tests (no network)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import pytest

from gli4py.enumerator import cli


def test_parser_defaults():
    args = cli.build_parser().parse_args([])
    assert args.no_ssh is False
    assert args.dangerous is False
    assert args.unredacted is False


def test_resolve_brute_tiers():
    p = cli.build_parser()
    assert cli.resolve_brute(p.parse_args([])) == ("off", False)
    assert cli.resolve_brute(p.parse_args(["--dangerous"])) == ("dangerous", False)
    assert cli.resolve_brute(p.parse_args(["--dangerous-full"])) == ("dangerous_full", False)
    assert cli.resolve_brute(p.parse_args(["--dangerous-full", "--include-destructive"])) == ("dangerous_full", True)


def test_output_dir_redacted_vs_unredacted():
    p = cli.build_parser()
    assert cli.output_dir_for(p.parse_args([]), redacted=True) == "docs/devices"
    with pytest.raises(SystemExit):
        cli.output_dir_for(p.parse_args(["--unredacted"]), redacted=False)
    assert cli.output_dir_for(p.parse_args(["--unredacted", "--output-dir", "/tmp/x"]), redacted=False) == "/tmp/x"


def test_help_runs():
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_enum_cli.py -v`
Expected: `ModuleNotFoundError` / `AttributeError`.

- [ ] **Step 3: Implement CLI + re-exports + packaging**

Create `gli4py/enumerator/cli.py`:

```python
"""gli4py-enumerate command-line interface."""

import argparse
import asyncio
import os
import sys
from typing import Any

import aiohttp

from ..glinet import GLinet
from .models import Caller, DeviceReport
from .probe import device_id, enumerate_device
from .report import summary_lines, to_json, to_markdown
from .ssh import SshUnavailable, ssh_discover


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    p = argparse.ArgumentParser(prog="gli4py-enumerate", description="Enumerate a GL.iNet device's RPC API surface.")
    p.add_argument("--host")
    p.add_argument("--username")
    p.add_argument("--password")
    p.add_argument("--env-file")
    p.add_argument("--output-dir")
    p.add_argument("--no-ssh", action="store_true")
    p.add_argument("--ssh-password")
    p.add_argument("--ssh-key")
    p.add_argument("--ssh-port", type=int, default=22)
    p.add_argument("--dangerous", action="store_true")
    p.add_argument("--dangerous-full", dest="dangerous_full", action="store_true")
    p.add_argument("--include-destructive", dest="include_destructive", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--unredacted", action="store_true")
    return p


def resolve_brute(args: argparse.Namespace) -> tuple[str, bool]:
    """Map flags to (brute_mode, include_destructive)."""
    if args.dangerous_full:
        return "dangerous_full", bool(args.include_destructive)
    if args.dangerous:
        return "dangerous", False
    return "off", False


def output_dir_for(args: argparse.Namespace, *, redacted: bool) -> str:
    """docs/devices for redacted output; require --output-dir for unredacted."""
    if args.output_dir:
        return args.output_dir
    if not redacted:
        raise SystemExit("--unredacted requires --output-dir (do not write secrets under docs/).")
    return "docs/devices"


def _load_env(env_file: str | None) -> None:
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return
    load_dotenv(env_file) if env_file else load_dotenv()


def _config(args: argparse.Namespace) -> dict[str, str]:
    return {
        "host": (args.host or os.environ.get("GLINET_HOST", "http://192.168.8.1")).rstrip("/"),
        "username": args.username or os.environ.get("GLINET_USERNAME", "root"),
        "password": args.password or os.environ.get("GLINET_PASSWORD", ""),
    }


def _make_caller(session: aiohttp.ClientSession, rpc_url: str, sid: str) -> Caller:
    async def caller(service: str, method: str, args: dict[str, Any] | None) -> dict[str, Any]:
        params: list[Any] = [sid, service, method]
        if args is not None:
            params.append(args)
        payload = {"jsonrpc": "2.0", "id": 0, "method": "call", "params": params}
        async with session.post(rpc_url, json=payload) as resp:
            data: dict[str, Any] = await resp.json(content_type=None)
            return data
    return caller


async def _run(args: argparse.Namespace) -> DeviceReport:
    cfg = _config(args)
    rpc_url = f"{cfg['host']}/rpc"
    host_only = cfg["host"].replace("https://", "").replace("http://", "").split("/")[0]

    surface = None
    if not args.no_ssh:
        try:
            surface = await ssh_discover(
                host_only, username="root",
                password=args.ssh_password or cfg["password"],
                key_filename=args.ssh_key, port=args.ssh_port,
            )
        except SshUnavailable as exc:
            print(f"[ssh] skipped: {exc}", file=sys.stderr)

    glinet = GLinet(base_url=rpc_url)
    await glinet.login(cfg["username"], cfg["password"])
    sid = glinet.sid or ""
    async with aiohttp.ClientSession() as session:
        caller = _make_caller(session, rpc_url, sid)
        info_env = await caller("system", "get_info", None)
        device_info = info_env.get("result") if isinstance(info_env.get("result"), dict) else {}
        brute, include_destructive = resolve_brute(args)
        return await enumerate_device(
            caller,
            redact_values=not args.unredacted,
            device_info=device_info,
            brute=brute,
            include_destructive=include_destructive,
            ssh_surface=surface,
        )


def main(argv: list[str] | None = None) -> int:
    """Entry point for `gli4py-enumerate`."""
    args = build_parser().parse_args(argv)
    _load_env(args.env_file)
    brute, include_destructive = resolve_brute(args)
    if brute == "dangerous_full" and not args.yes:
        verb = "destructive + " if include_destructive else ""
        resp = input(f"--dangerous-full will issue {verb}mutating calls. Type 'yes' to continue: ")
        if resp.strip().lower() != "yes":
            print("Aborted.")
            return 1
    if args.unredacted:
        print("WARNING: --unredacted captures secrets; do NOT commit the output.", file=sys.stderr)

    out_dir = output_dir_for(args, redacted=not args.unredacted)
    report = asyncio.run(_run(args))

    os.makedirs(out_dir, exist_ok=True)
    did = device_id(report.device)
    with open(os.path.join(out_dir, f"{did}.json"), "w", encoding="utf-8") as fh:
        fh.write(to_json(report))
    with open(os.path.join(out_dir, f"{did}.md"), "w", encoding="utf-8") as fh:
        fh.write(to_markdown(report))
    print("\n".join(summary_lines(report)))
    print(f"\nWrote {out_dir}/{did}.json and .md")
    return 0
```

Update `gli4py/enumerator/__init__.py`:

```python
"""GL.iNet device API enumerator (catalog + SSH + brute-force discovery)."""

from .models import DeviceReport, ProbeStatus, Risk
from .probe import enumerate_device

__all__ = ["enumerate_device", "DeviceReport", "ProbeStatus", "Risk"]
```

Update `pyproject.toml`:
- Add under `[project]` (new table):
```toml
[project.scripts]
gli4py-enumerate = "gli4py.enumerator.cli:main"

[project.optional-dependencies]
cli = ["python-dotenv>=1.0"]
ssh = ["paramiko>=3"]
enumerate = ["gli4py[cli,ssh]"]
```
- Extend the mypy override module list to include paramiko:
```toml
[[tool.mypy.overrides]]
module = ["uplink", "passlib", "passlib.*", "paramiko"]
ignore_missing_imports = true
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_enum_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Full gate + entry-point smoke test**

Run:
```bash
uv sync
uv run gli4py-enumerate --help
uv run mypy gli4py && uv run ruff check . && uv run ruff format --check . && uv run pytest -q
uv run --with pylint pylint --disable=import-error,fixme,line-too-long,invalid-name,too-many-public-methods,abstract-method,overridden-final-method,too-many-instance-attributes,too-many-public-methods,too-few-public-methods,too-many-branches $(git ls-files '*.py')
```
Expected: `--help` prints usage; mypy/ruff/pytest clean; pylint `10.00` (add module-level `# pylint: disable=...` to any new test file that trips `missing-function-docstring`/`redefined-outer-name`/`protected-access`, per Global Constraints).

- [ ] **Step 6: Commit**

```bash
git add gli4py/enumerator/cli.py gli4py/enumerator/__init__.py pyproject.toml uv.lock tests/test_enum_cli.py
git commit -m "feat(enumerator): gli4py-enumerate CLI + packaging (scripts, extras)"
```

---

### Task 10: Live smoke (manual, optional) + README note

**Files:**
- Modify: `README.md` (document the command)
- Test: manual live run (needs a device + `.env`); not in CI.

- [ ] **Step 1: Manual live run (if a device is available)**

Run (read-only; SSH auto if reachable):
```bash
uv run gli4py-enumerate
```
Expected: prints a summary (counts + not-yet-wrapped list) and writes `docs/devices/<id>.json` + `.md`. Spot-check the Markdown lists services like `firewall`, `flow_statistics`, `modem`; confirm no secrets appear in the redacted output (`grep -iE 'private_key|"key"' docs/devices/<id>.json` shows `<redacted>`).

- [ ] **Step 2: Add a README section**

Add to `README.md` a short "Enumerating a device" section: install with `pip install 'gli4py[enumerate]'`, configure `.env` (or flags), run `gli4py-enumerate`; note SSH auto-discovery, `--no-ssh`, the `--dangerous*` tiers and their gating, and `--unredacted` (+ "do not commit") . Keep it ≤25 lines.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document gli4py-enumerate"
```

> Do NOT commit any `docs/devices/*.json|md` produced by a live run unless you have reviewed them for secrets and want them in the repo.

---

## Self-Review

**1. Spec coverage**

| Spec requirement | Task |
|---|---|
| Catalog probe (read-only) | 3 (catalog), 4 (engine) |
| Risk-classified catalog (READ/WRITE/DANGEROUS/ACTIVE) | 3 |
| Classifier (-32601/-32602/-32000/-1/other/exception) | 1 |
| Redaction default + `--unredacted` + schema | 2, 9 |
| Coverage / gap analysis | 3 (map), 5 (not-wrapped section) |
| JSON + Markdown + terminal summary under docs/devices | 5, 9 |
| `--ssh` auto, read-only, handlers+validators+oui.db+features, confirm-via-probe | 7 (parse), 8 (discover+merge), 9 (auto/`--no-ssh`) |
| `--discover-acl` | Deferred — see note below |
| `--dangerous`/`--dangerous-full`/`--include-destructive` gating + wordlists + confirmation | 6 (plan/brute), 9 (flags+confirm) |
| Shipped console entry point + optional extras + lean core | 9 |
| mypy --strict / ruff / pylint clean | every task's step 5 |
| Reuse GLinet.login only; no library API change | 9 (`_run`) |
| Unit-testable without hardware (injectable caller, pure parsers) | 4,5,6,7,8 |

**Gap noted:** `--discover-acl` (spec tier 3) is **not** implemented in Tasks 1–10. It was verified blocked on the gl-ngx gateway and is fully superseded by `--ssh` (which reads the same files directly). Per YAGNI it is intentionally deferred; if you want it, add a task that probes `file list`/`file read` via the caller and parses any returned ACL JSON — but it returns `-32601` on tested firmware. **Confirm this deferral is acceptable, or I add the task.**

**2. Placeholder scan:** The only intentional "port the rest" is Task 3's catalog, which points at the committed authoritative data file `2026-06-26-glinet-api-catalog.md` and is enforced by the integrity tests — not a vague placeholder. All code steps contain complete code.

**3. Type consistency:** `Caller`, `MethodReport`, `DeviceReport`, `SshSurface`, `Risk`, `ProbeStatus` are defined in Task 1 (`models.py`) and used with the same signatures throughout. `enumerate_device` grows keyword-only params across Tasks 4/6/8 (never changing earlier ones). `device_id`, `classify`, `redact`, `schema_of`, `is_read_method`, `risk_of`, `covered_by`, `brute_plan`, `parse_handlers`, `parse_validators`, `parse_account_acl`, `ssh_discover`, `to_json`/`to_markdown`/`summary_lines`, `build_parser`/`resolve_brute`/`output_dir_for`/`main` are referenced with consistent names/signatures across tasks.

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review between tasks (`superpowers:subagent-driven-development`).
2. **Inline Execution** — work the tasks in this session with checkpoints (`superpowers:executing-plans`).
