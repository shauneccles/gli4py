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
