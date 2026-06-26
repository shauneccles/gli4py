# gli4py
A aysnc python 3 API wrapper for GL-inet routers with version 4 firmware. [WIP]

[GL-inet](https://www.gl-inet.com/) routers are built on [OpenWRT](https://openwrt.org/). They are highly customizeable but have an attractive user interface.

As part of their modiification of the UI they used to provide a [documented locally accessible API](https://web.archive.org/web/20240121142533/https://dev.gl-inet.com/router-4.x-api/).

I thought it would be handy to develop a python 3 wrapper for the API for easy intergation into other services such as [HomeAssistant](https://www.home-assistant.io/)

## Installation
`pip install gli4py`

### Enumerating a device

Install with one of the optional extras:
```bash
pip install 'gli4py[enumerate]'  # or [ssh], [cli]
```

Configure via `.env` file (or use `--host`, `--username`, `--password` flags):
```
GLINET_HOST=http://192.168.8.1
GLINET_USERNAME=root
GLINET_PASSWORD=<your_password>
```

Run `uv run gli4py-enumerate` (or just `gli4py-enumerate` once installed). It writes `docs/devices/<id>.json` and `.md` files and prints a summary.

**SSH auto-discovery** runs automatically when SSH credentials work (web password typically serves as SSH root), reading the device's handler dir, validators, and oui.db directly for ground-truth. Disable with `--no-ssh`.

**Brute-force tiers** (`--dangerous` / `--dangerous-full` / `--include-destructive`) probe mutating methods. Read-only by default; `--dangerous-full` prompts for confirmation (`--yes` to skip). Destructive methods require `--include-destructive`.

Use `--unredacted` to capture raw credential values (default redacts). **Do NOT commit unredacted output.**

## Dev setup
1. Clone the repo
2. Ensure you have Python 3.11 or greater (`python3 -V`) and install [uv](https://docs.astral.sh/uv/).
3. `uv sync` — creates the in-project `.venv` and installs the runtime + dev dependencies.
4. The tests run against a **live router**, so copy `.env.example` to `.env` and set at least
   `GLINET_PASSWORD` (and `GLINET_HOST` if not `192.168.8.1`). Without it the live suite is skipped.
5. `uv run pytest -s` to see responses.
6. Build with `uv build`. Releases publish to PyPI automatically on a GitHub Release (trusted publishing).

## Dev setup alongside HA & the Custom component
1. Clone the repo into the vscode `/workspaces/` dir
2. The inside the `ha-env` terminal run `(ha-venv) vscode ➜ /workspaces/core (branch-name) $ pip install -e /workspaces/gli4py `
3. Ensure the custom component has `"python.analysis.extraPaths": ["/workspaces/gli4py/"]` in `.vscode/settings.json`
4. deactivate the `ha-env` with `deactivate`
5. Do steps 3 onwards above

Todo list:
- [ ] Decide on useful endpoints to expose - see https://github.com/HarvsG/ha-glinet-integration#todo
- [ ] Expose said endpoints
- [ ] Write remaining
- [x] Package correctly
- [x] Test that dev enviroment is re-producable
- [x] Publish on pip
- [ ] Static typing
