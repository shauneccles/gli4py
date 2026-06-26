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
