"""Tests for the Pages site dataset build (sanitizing projection)."""
# pylint: disable=missing-function-docstring,redefined-outer-name

import json

from scripts.build_site_data import build, build_manifest, project_report

RAW = {
    "device": {
        "model": "mt6000",
        "firmware_version": "4.9.0",
        "vendor": "GL.iNet",
        "device_type": "router",
        "hardware_version": "1.0",
        "mac": "94:83:C4:AA:BB:CC",
        "sn": "SECRET123",
        "sn_bak": "SECRET456",
        "country_code": "US",
        "hidden_features": [],
    },
    "services": {
        "system": {
            "get_info": {
                "status": "available",
                "error_code": None,
                "risk": "read",
                "discovered_by": "catalog",
                "covered_by": "router_info",
                "params": None,
                "schema": {"model": "str"},
                "value": {"mac": "94:83:C4:AA:BB:CC", "sn": "SECRET123"},
            },
        },
        "firewall": {
            "get_rule_list": {
                "status": "available",
                "error_code": None,
                "risk": "read",
                "discovered_by": "catalog",
                "covered_by": None,
                "params": None,
                "schema": {"res": "list"},
                "value": {"res": []},
            },
            "set_rule": {
                "status": "absent",
                "error_code": -32601,
                "risk": "write",
                "discovered_by": "catalog",
                "covered_by": None,
                "params": None,
                "schema": None,
                "value": None,
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
    assert entry["available_count"] == 2  # system.get_info + firewall.get_rule_list
    assert entry["service_count"] == 2  # both services have a present method
    assert entry["not_wrapped_count"] == 1  # firewall.get_rule_list (covered_by None)


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
