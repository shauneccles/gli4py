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
    assert cli.resolve_brute(p.parse_args(["--dangerous-full", "--include-destructive"])) == (
        "dangerous_full",
        True,
    )


def test_output_dir_redacted_vs_unredacted():
    p = cli.build_parser()
    assert cli.output_dir_for(p.parse_args([]), redacted=True) == "docs/devices"
    with pytest.raises(SystemExit):
        cli.output_dir_for(p.parse_args(["--unredacted"]), redacted=False)
    assert (
        cli.output_dir_for(p.parse_args(["--unredacted", "--output-dir", "/tmp/x"]), redacted=False)
        == "/tmp/x"
    )


def test_help_runs():
    with pytest.raises(SystemExit) as e:
        cli.main(["--help"])
    assert e.value.code == 0
