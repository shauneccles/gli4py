"""gli4py-enumerate command-line interface."""

import argparse
import asyncio
import os
import sys
from typing import Any

import aiohttp
from uplink import AiohttpClient

from ..glinet import GLinet
from .models import Caller, DeviceReport
from .probe import device_id, enumerate_device
from .report import summary_lines, to_json, to_markdown
from .ssh import SshUnavailable, ssh_discover


def build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser."""
    p = argparse.ArgumentParser(
        prog="gli4py-enumerate", description="Enumerate a GL.iNet device's RPC API surface."
    )
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
        return str(args.output_dir)
    if not redacted:
        raise SystemExit("--unredacted requires --output-dir (do not write secrets under docs/).")
    return "docs/devices"


def _load_env(env_file: str | None) -> None:
    """Load a .env file if python-dotenv is available (optional [cli] extra)."""
    try:
        from dotenv import load_dotenv  # pylint: disable=import-outside-toplevel
    except ImportError:
        return
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()


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
                host_only,
                username="root",
                password=args.ssh_password or cfg["password"],
                key_filename=args.ssh_key,
                port=args.ssh_port,
            )
        except SshUnavailable as exc:
            print(f"[ssh] skipped: {exc}", file=sys.stderr)

    async with aiohttp.ClientSession() as session:
        glinet = GLinet(base_url=rpc_url, client=AiohttpClient(session=session))
        await glinet.login(cfg["username"], cfg["password"])
        sid = glinet.sid or ""
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
