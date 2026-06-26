"""Async enumeration engine: probe a device through an injectable caller."""

import re
from typing import Any

from .catalog import CATALOG, COMMON_READ_METHODS, is_read_method
from .classify import classify
from .coverage import covered_by
from .models import Caller, DeviceReport, MethodReport, ProbeStatus, Risk
from .redact import redact, schema_of

_SLUG = re.compile(r"[^a-z0-9.]+")


def device_id(device: dict[str, Any]) -> str:
    """Slug `model_firmware` from a get_info dict, with fallbacks."""
    model = device.get("model") or device.get("device_type") or device.get("board_info") or "unknown"
    firmware = device.get("firmware_version") or "unknown"
    model_slug = _SLUG.sub("-", model.lower()).strip("-")
    firmware_slug = _SLUG.sub("-", firmware.lower()).strip("-")
    return f"{model_slug}_{firmware_slug}"


async def _probe(caller: Caller, service: str, method: str) -> tuple[ProbeStatus, int | None, object]:
    try:
        envelope = await caller(service, method, None)
    except Exception:  # pylint: disable=broad-except
        return ProbeStatus.UNREACHABLE, None, None
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
                risk=risk,
                discovered_by="catalog",
                params=None,
                schema=schema_of(value) if value is not None else None,
                value=redact(value, enabled=redact_values) if value is not None else None,
                covered_by=covered_by(service, method),
            )
        )
    return DeviceReport(device=device_info, methods=methods)
