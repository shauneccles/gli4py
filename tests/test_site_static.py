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
