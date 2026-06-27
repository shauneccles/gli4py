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


def _sanitize_schema(obj: Any) -> Any:
    """Recursively drop dict keys named 'value' from schema objects.

    Schema shapes can legitimately have a field named 'value' (e.g. select-option
    objects {label: str, value: int}), but the key name collides with the
    per-method 'value' field that holds actual device responses and must not be
    published.  Dropping these keys keeps the shape description while ensuring
    no 'value' key appears anywhere in the published JSON.
    """
    if isinstance(obj, dict):
        return {k: _sanitize_schema(v) for k, v in obj.items() if k != "value"}
    if isinstance(obj, list):
        return [_sanitize_schema(item) for item in obj]
    return obj


def project_report(raw: dict[str, Any], device_id_str: str) -> dict[str, Any]:
    """Project a raw enumerator report to the publishable, sanitized surface."""
    device = raw.get("device", {})
    out: dict[str, Any] = {"id": device_id_str}
    for field in _DEVICE_FIELDS:
        if field in device:
            out[field] = device[field]
    out["services"] = {
        service: {
            method: {
                field: (
                    _sanitize_schema(rec.get(field))
                    if field == "schema"
                    else rec.get(field)
                )
                for field in _METHOD_FIELDS
            }
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
    parser = argparse.ArgumentParser(
        description="Build the Pages API dataset from enumerator reports."
    )
    parser.add_argument("--reports", default="docs/devices")
    parser.add_argument("--out", default="site/data")
    args = parser.parse_args(argv)
    count = build(Path(args.reports), Path(args.out))
    print(f"Wrote {count} device(s) to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
