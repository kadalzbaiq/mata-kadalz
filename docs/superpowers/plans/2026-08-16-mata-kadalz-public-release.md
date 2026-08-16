# mata-kadalz Public Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generalize the private `vision-mcp` server into a public, installable, multi-host MCP server (`mata-kadalz`) with dual transport (stdio + streamable HTTP), per-OS setup scripts, full docs, and maximized GitHub features.

**Architecture:** Copy the validated single-file `server.py` from `vision-mcp` and generalize it: (1) dual transport — `--transport stdio|http` selecting `Server.run` (stdio) vs `Server.streamable_http_app` + `uvicorn` (HTTP, path `/mcp`); (2) host auto-detection — WSL detects gateway IP, native Linux/Mac/Windows default `127.0.0.1`, `LLAMA_SERVER_URL` env overrides all; (3) a `mata-kadalz` console entry point. Model combo (Qwen3-VL Q4_K_M + mmproj F16) and the single `vision.inspect` tool are frozen.

**Tech Stack:** Python >=3.11, `mcp==2.0.0` (stdlib-only server logic; uvicorn ships as a transitive dep), uv, bash + PowerShell setup scripts, GitHub Actions CI.

**Spec:** `docs/superpowers/plans/2026-08-16-mata-kadalz-public-release.md` (this file is the plan AND the design record; the approved design lives in the conversation).

## Global Constraints

- **Model is frozen:** `Qwen3VL-4B-Instruct-Q4_K_M.gguf` + `mmproj-Qwen3VL-4B-Instruct-F16.gguf` from `Qwen/Qwen3-VL-4B-Instruct-GGUF`. Never change.
- **One tool only:** `vision.inspect(image_path, task)`. No new tools.
- **Cache contract:** key = `sha256(sha256(image) + task + model_id)`; failed requests never cached; inference serialized via `asyncio.Lock`; never return image bytes (text JSON only).
- **Config precedence:** `DEFAULTS` < `config/config.json` (empty values skipped) < env vars. Relative config paths resolve against repo root (`BASE_DIR`).
- **CLI entry:** console script `mata-kadalz` (from `[project.scripts]`), equivalent to `python server.py`.
- **Transports:** `--transport stdio` (default) and `--transport http` (streamable HTTP at `--path /mcp`, `--host 127.0.0.1`, `--port 9932`). `--once` self-check preserved.
- **Host detection:** `_detect_gateway_ip()` returns `127.0.0.1` unless running inside WSL (detect via `WSL_DISTRO_NAME` env or `/proc/version` containing "microsoft"), where it parses `ip route` default gateway. `LLAMA_SERVER_URL` env/config wins over detection.
- **Repo:** public `kadalzbaiq/mata-kadalz`, default branch `main`, ruleset `protect-main` already active (requires CI status check context `ci`), repo created from `repo-template` with `setup.sh` applied.
- **Master copy:** the private `vision-mcp` repo stays untouched and stays the personal tuning ground; `mata-kadalz` is a fork-in-spirit.
- **Dependency boundary (MCP ≠ inference runtime ≠ model):** `mata-kadalz` is the MCP layer ONLY. `llama.cpp` and the Qwen model/mmproj are **external dependencies**, installed and managed by the user per the docs. The repo MUST NOT vendor llama.cpp, commit binaries/GGUF/mmproj, package them into releases, auto-download them during MCP install, or own model lifecycle. The MCP connects to an already-running `llama-server` over HTTP. Doc commands are *instructions for the user*, never executed by the package.

---

### Task 0: Verify scaffolding & seed source files

**Files:**
- Verify: `/home/kadalz/dev/mata-kadalz` (public repo, ruleset active, labels present)
- Copy from `/home/kadalz/vision-mcp`: `server.py`, `pyproject.toml`, `config/config.json`, `tests/test_vision.py`, `LICENSE` (keep template's), `.gitignore` merge. **Do NOT copy `scripts/*`** — they are llama.cpp/model distribution tooling (install.sh, llama-manage.sh, start-llama-server.*, download-*) and stay out of `mata-kadalz` per the dependency boundary.

**Interfaces:**
- Consumes: nothing (repo scaffold exists)
- Produces: seed files present at repo root so later tasks edit them

- [ ] **Step 1: Verify scaffold**

```bash
cd /home/kadalz/dev/mata-kadalz
git branch --show-current        # expect main
gh ruleset list -R kadalzbaiq/mata-kadalz   # expect protect-main active
gh label list -R kadalzbaiq/mata-kadalz     # expect bug/enhancement/good-first-issue
```

Expected: main branch, active `protect-main` ruleset (status check context `ci`), labels present.

- [ ] **Step 2: Copy seed files from private repo**

```bash
cd /home/kadalz/dev/mata-kadalz
cp /home/kadalz/vision-mcp/server.py .
cp /home/kadalz/vision-mcp/pyproject.toml .
cp /home/kadalz/vision-mcp/config/config.json .
cp /home/kadalz/vision-mcp/tests/test_vision.py tests/test_vision.py 2>/dev/null || (mkdir -p tests && cp /home/kadalz/vision-mcp/tests/test_vision.py tests/)
```

Expected: files copied. (Contents will be rewritten/generalized in Tasks 1–4. **No scripts are seeded** — the llama.cpp/manage scripts from the private repo are distribution tooling and stay out of `mata-kadalz` per the dependency boundary.)

- [ ] **Step 3: Create venv to run tests later**

```bash
cd /home/kadalz/dev/mata-kadalz
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install "mcp==2.0.0" "pytest>=8.0"
```

Expected: `.venv` with mcp 2.0.0 + pytest (copies current private-repo runtime so all tests run identically).

- [ ] **Step 4: Commit**

```bash
cd /home/kadalz/dev/mata-kadalz
git add server.py pyproject.toml config tests .gitignore
git commit -m "chore: seed from private vision-mcp (server, tests, config)"
```

---

### Task 1: Dual transport + host detection + CLI entry in `server.py`

**Files:**
- Modify: `server.py`

**Interfaces:**
- Consumes: seed `server.py`
- Produces:
  - `cli()` — sync console entry point (wraps `asyncio.run(main())`)
  - `main()` — async, argparse: `--transport {stdio,http}`, `--host`, `--port`, `--path`, `--once`
  - `_detect_gateway_ip()` — `127.0.0.1` unless WSL, then `ip route` gateway
  - HTTP branch: `server.streamable_http_app(streamable_http_path=args.path)` run via `uvicorn.run`

- [ ] **Step 1: Write the failing tests for transport + host detection**

Append to `tests/test_vision.py`:

```python
def test_wsl_not_detected_native(monkeypatch):
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setattr(server, "_is_wsl", lambda: False)
    assert server._detect_gateway_ip() == "127.0.0.1"


def test_wsl_detection_via_env(monkeypatch):
    monkeypatch.setenv("WSL_DISTRO_NAME", "Ubuntu")
    assert server._is_wsl() is True


def test_http_app_buildable():
    srv = server._build_server()
    app = srv.streamable_http_app(streamable_http_path="/mcp")
    assert app is not None


def test_cli_parses_transport():
    args = server._parse_args(["--transport", "http", "--port", "9999"])
    assert args.transport == "http"
    assert args.port == 9999


def test_cli_default_stdio():
    args = server._parse_args([])
    assert args.transport == "stdio"
    assert args.path == "/mcp"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_vision.py -v`
Expected: FAIL — `_is_wsl`, `_build_server`, `_parse_args` not defined; `_detect_gateway_ip` returns gateway instead of `127.0.0.1` on native.

- [ ] **Step 3: Implement transport + host detection**

In `server.py`:

```python
import platform

def _is_wsl():
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _detect_gateway_ip():
    if not _is_wsl():
        return "127.0.0.1"
    try:
        out = subprocess.run(
            ["ip", "route"], capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            if line.startswith("default"):
                return line.split()[2]
    except Exception:
        pass
    return "127.0.0.1"
```

- [ ] **Step 4: Refactor server construction + CLI args**

Replace the `main()` body so it splits into `_build_server()`, `_parse_args()`, `cli()`, `main()`:

```python
def _build_server():
    return Server(
        "mata-kadalz",
        version="1.0.0",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="mata-kadalz",
        description="Local vision MCP server (Qwen3-VL via llama-server). stdio or streamable HTTP.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9932, help="HTTP bind port (default: 9932)")
    parser.add_argument("--path", default="/mcp", help="streamable HTTP path (default: /mcp)")
    parser.add_argument(
        "--once", action="store_true", help="read one request from stdin and exit"
    )
    return parser.parse_args(argv)


def cli():
    asyncio.run(main())


async def main():
    args = _parse_args()

    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging()

    if args.once:
        line = sys.stdin.buffer.readline()
        params = json.loads(line)
        res = await _inspect(params["image_path"], params["task"])
        print(json.dumps(json.loads(res.content[0].text)))
        return

    server = _build_server()

    if args.transport == "http":
        import uvicorn

        app = server.streamable_http_app(streamable_http_path=args.path)
        log.info("serving streamable HTTP on %s:%s%s", args.host, args.port, args.path)
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
        return

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )
```

- [ ] **Step 5: Update `__main__` guard**

```python
if __name__ == "__main__":
    cli()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vision.py -v`
Expected: ALL PASS (11 original + 5 new).

- [ ] **Step 7: Verify stdio handshake still works (no llama-server needed for handshake)**

```bash
cd /home/kadalz/dev/mata-kadalz
printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' | .venv/bin/python server.py --transport stdio
```

Expected: `initialize` result echoes back, process exits cleanly (no crash).

- [ ] **Step 8: Verify HTTP transport boots**

```bash
cd /home/kadalz/dev/mata-kadalz
timeout 6 .venv/bin/python server.py --transport http --port 9932 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:9932/mcp
kill %1 2>/dev/null || true
```

Expected: HTTP status 4xx/5xx on bare POST to `/mcp` (any non-5xx-connection error proves the ASGI app is up; exact body varies by MCP SDK).

- [ ] **Step 9: Commit**

```bash
cd /home/kadalz/dev/mata-kadalz
git add server.py tests/test_vision.py
git commit -m "feat: dual transport (stdio+http) with CLI entry and WSL host detection"
```

---

### Task 2: Generalize `pyproject.toml` (name, entry point, description)

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Task 1 `cli()`
- Produces: installable package `mata-kadalz` with console script

- [ ] **Step 1: Rewrite pyproject**

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "mata-kadalz"
version = "1.0.0"
description = "Lizard Eyes: local vision MCP server (Qwen3-VL via llama-server). stdio + streamable HTTP."
requires-python = ">=3.11"
license = "MIT"
dependencies = [
    "mcp==2.0.0",
]

[project.scripts]
mata-kadalz = "server:cli"

[tool.setuptools]
py-modules = ["server"]

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra"
```

- [ ] **Step 2: Verify console script works**

```bash
cd /home/kadalz/dev/mata-kadalz
.venv/bin/pip install -e .
.venv/bin/mata-kadalz --help
```

Expected: `--help` shows the argparse help (prog `mata-kadalz`).

- [ ] **Step 3: Commit**

```bash
cd /home/kadalz/dev/mata-kadalz
git add pyproject.toml
git commit -m "feat: mata-kadalz package with console entry point"
```

---

### Task 3: Platform detection + llama-server connectivity helpers

**Files:**
- Modify: `server.py` (add `_detect_platform()`, `_check_llama_server()`, CLI `--health` flag)
- Modify: `tests/test_vision.py` (tests for the new helpers)
- Create: `scripts/install.sh` (installs the MCP package ONLY — no llama.cpp/model downloads)

**Interfaces:**
- Consumes: Task 1 `_is_wsl()`; resolved `_SERVER_URL` from config precedence
- Produces:
  - `_detect_platform() -> dict` with keys `os`, `arch`, `wsl`
  - `_check_llama_server(url, timeout=5) -> dict` with keys `reachable`, `status`, `health_url`, optional `error`
  - `mata-kadalz --health` — prints `{platform, llama_server_url, health}` and exits 0 if reachable, 1 otherwise

**Boundary note:** NO downloaders, NO llama.cpp installer, NO model fetcher. `install.sh` only creates a venv and installs the `mata-kadalz` package. llama.cpp/model install/start commands live in `docs/` as instructions for the user (Task 4).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_vision.py`:

```python
def test_detect_platform_shape():
    p = server._detect_platform()
    assert set(p) == {"os", "arch", "wsl"}
    assert p["os"] in {"linux", "darwin", "windows"}
    assert isinstance(p["wsl"], bool)


def test_check_llama_server_ok(monkeypatch):
    class FakeResp:
        status = 200
        def read(self):
            return b'{"status":"ok"}'
    def fake_urlopen(req, timeout=5):
        return FakeResp()
    monkeypatch.setattr(server.urllib.request, "urlopen", fake_urlopen)
    r = server._check_llama_server("http://127.0.0.1:9931")
    assert r["reachable"] is True
    assert r["status"] == 200


def test_check_llama_server_unreachable(monkeypatch):
    def boom(req, timeout=5):
        raise urllib.error.URLError("connection refused")
    monkeypatch.setattr(server.urllib.request, "urlopen", boom)
    r = server._check_llama_server("http://127.0.0.1:9999")
    assert r["reachable"] is False
    assert "error" in r


def test_cli_parses_health():
    args = server._parse_args(["--health"])
    assert args.health is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_vision.py -v`
Expected: FAIL — `_detect_platform`, `_check_llama_server` not defined; `_parse_args` has no `--health`.

- [ ] **Step 3: Implement platform detection + health check**

In `server.py`, after `_is_wsl()`:

```python
def _detect_platform():
    return {
        "os": platform.system().lower(),
        "arch": platform.machine().lower(),
        "wsl": _is_wsl(),
    }


def _check_llama_server(url, timeout=5):
    url = url.rstrip("/")
    health_url = f"{url}/health"
    try:
        with urllib.request.urlopen(health_url, timeout=timeout) as resp:
            return {
                "reachable": True,
                "status": resp.status,
                "health_url": health_url,
                "body": resp.read().decode()[:200],
            }
    except urllib.error.HTTPError as e:
        return {
            "reachable": False,
            "status": e.code,
            "health_url": health_url,
            "error": str(e),
        }
    except Exception as e:
        return {
            "reachable": False,
            "status": None,
            "health_url": health_url,
            "error": str(e),
        }
```

Add `--health` to `_parse_args()`:

```python
    parser.add_argument(
        "--health",
        action="store_true",
        help="print platform, resolved LLAMA_SERVER_URL, and llama-server health; exit 0 if reachable",
    )
```

Handle `--health` in `main()` before any server construction (after `--once`):

```python
    if args.health:
        check = _check_llama_server(_SERVER_URL)
        print(
            json.dumps(
                {
                    "platform": _detect_platform(),
                    "llama_server_url": _SERVER_URL,
                    "health": check,
                },
                indent=2,
            )
        )
        return
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_vision.py -v`
Expected: ALL PASS (11 original + 4 new from Task 1 + 4 new here).

- [ ] **Step 5: Verify `--health` CLI behavior**

```bash
cd /home/kadalz/dev/mata-kadalz
.venv/bin/mata-kadalz --health; echo "exit=$?"
```

Expected: JSON with platform/os/arch/wsl, resolved `llama_server_url`, health dict; exit 0 if a llama-server is up at that URL, 1 otherwise. (On CI/clean machine: `reachable: false` + exit 1 is a valid result, not a failure.)

- [ ] **Step 6: Write `scripts/install.sh` (package install only)**

```bash
#!/usr/bin/env bash
# Install the mata-kadalz MCP server into a local venv.
# Installs ONLY this package. llama-server and the model are external
# dependencies — install them separately per docs/SETUP-*.md.
# Usage: ./scripts/install.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Install it first (e.g. sudo apt install python3 python3-venv)."
  exit 1
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .

mkdir -p runtime/vision/cache
echo "mata-kadalz installed."
echo "Check llama-server reachability:  .venv/bin/mata-kadalz --health"
echo "Run stdio:                        .venv/bin/mata-kadalz"
echo "Run http:                         .venv/bin/mata-kadalz --transport http --host 127.0.0.1 --port 9932"
echo "Self-check: echo '{\"image_path\":\"<img>\",\"task\":\"<task>\"}' | .venv/bin/mata-kadalz --once"
```

- [ ] **Step 7: Verify install.sh is idempotent + installs nothing external**

```bash
cd /home/kadalz/dev/mata-kadalz
bash scripts/install.sh
.venv/bin/mata-kadalz --help
```

Expected: re-install works; `--help` prints help; no llama.cpp/model files appear anywhere in the repo (verify: `find . -name "*.gguf" -o -name "llama-server*" | grep -v .venv` → empty).

- [ ] **Step 8: Commit**

```bash
cd /home/kadalz/dev/mata-kadalz
git add server.py tests/test_vision.py scripts/install.sh
git commit -m "feat: platform detection + llama-server health check; package-only install script"
```

---

### Task 4: README + per-host setup docs + AGENTS.md

**Files:**
- Rewrite: `README.md`
- Create: `docs/SETUP-windows.md`, `docs/SETUP-linux.md`, `docs/SETUP-macos.md`, `docs/SETUP-hybrid-wsl.md`, `docs/SETUP-modular.md`
- Rewrite: `AGENTS.md` (repo-specific, generalized)
- Update: `CONTEXT.md` glossary (fill in domain terms)

**Interfaces:**
- Consumes: all Tasks 1–3
- Produces: complete public docs; no code impact

- [ ] **Step 1: Write README.md**

Cover: one-liner ("Lizard Eyes — local vision MCP server backed by Qwen3-VL-4B"), architecture diagram (generic, not WSL-specific), supported host setups table, quick start per OS (link to docs/), client registration for all 3 clients × both transports, one-tool usage, config table (unchanged precedence), caching, self-check, tests, license.

Required content (exact):

```markdown
# mata-kadalz 🦎

Lizard Eyes — local **vision MCP server** backed by **Qwen3-VL-4B** running on `llama-server`.
Gives any MCP client (opencode, Claude, Codex, ...) one tool: `vision.inspect(image_path, task)`.

## Supported setups

| Host | llama-server runs on | Setup doc |
|---|---|---|
| Windows only | Windows (native) | `docs/SETUP-windows.md` |
| Linux only | Linux (native) | `docs/SETUP-linux.md` |
| macOS only | macOS (native) | `docs/SETUP-macos.md` |
| WSL2 on Windows | Windows host (native) | `docs/SETUP-hybrid-wsl.md` |
| Any / remote / custom | anywhere reachable over HTTP | `docs/SETUP-modular.md` |

## Client registration

stdio (local):

```bash
# opencode: config/open code entry
# claude
claude mcp add vision -- /path/to/.venv/bin/mata-kadalz
# codex
codex mcp add vision -- /path/to/.venv/bin/mata-kadalz
```

streamable HTTP (remote):

```bash
# claude
claude mcp add --transport http vision http://127.0.0.1:9932/mcp
# codex
codex mcp add vision --url http://127.0.0.1:9932/mcp
# opencode (opencode.json)
{ "mcp": { "vision": { "type": "remote", "url": "http://127.0.0.1:9932/mcp" } } }
```

opencode stdio:

```jsonc
{ "mcp": { "vision": { "type": "local",
  "command": ["/abs/path/mata-kadalz/.venv/bin/mata-kadalz"] } } }
```
```

(Continue with architecture, model, layout, usage, config table, caching, self-check, test, license — mirror the private README but generic paths.)

- [ ] **Step 2: Write the 5 setup docs**

Each `docs/SETUP-<host>.md` follows the same template. **llama.cpp and the model are installed by the USER from official sources; the docs link out, never redistribute or auto-download.** The MCP's own `install.sh` only installs the `mata-kadalz` package.

```markdown
# Setup: <Host>

This guide covers running `mata-kadalz` on <Host>. Two parts:

**A. External backend (llama-server + model)** — installed once, by you,
from official sources. `mata-kadalz` only connects to the running server; it
never downloads or bundles these.

**B. mata-kadalz (MCP layer)** — the installable package from this repo.

## A. llama-server + model (external)

1. Install **llama.cpp** following its official docs for your platform:
   https://github.com/ggml-org/llama.cpp#readme (releases:
   https://github.com/ggml-org/llama.cpp/releases) — install the `llama-server`
   binary, do NOT install it via this repo.
2. Download the **model** (LLM) from Hugging Face:
   `Qwen3VL-4B-Instruct-Q4_K_M.gguf` —
   https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/Qwen3VL-4B-Instruct-Q4_K_M.gguf
3. Download the **mmproj** (vision encoder):
   `mmproj-Qwen3VL-4B-Instruct-F16.gguf` —
   https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-4B-Instruct-F16.gguf
   (Place both where your llama.cpp install expects them.)
4. Start `llama-server` with your model + mmproj, e.g.:

   ```bash
   llama-server -m Qwen3VL-4B-Instruct-Q4_K_M.gguf --mmproj mmproj-Qwen3VL-4B-Instruct-F16.gguf \
     --host 0.0.0.0 --port 9931 -c 8192 -t 8 --parallel 1 --image-min-tokens 1024
   ```

   (This is an example for you to run; your exact flags come from llama.cpp docs.)
5. Verify it is healthy: `curl http://localhost:9931/health` → `{"status":"ok"}`.

## B. mata-kadalz (MCP layer)

1. Install Python >=3.11.
2. Install the MCP server: `./scripts/install.sh` (creates `.venv`, installs the `mata-kadalz` package only).
3. Point it at llama-server: the default `http://127.0.0.1:9931` works for the
   common case. Override in `config/config.json` or env `LLAMA_SERVER_URL`
   (see README "Configuration").
4. Confirm connectivity: `.venv/bin/mata-kadalz --health` → `"reachable": true`.
5. Register in your client (stdio or http) — see README "Client registration".
6. Self-check: `echo '{"image_path":"/abs/path/img.png","task":"describe"}' | .venv/bin/mata-kadalz --once`
```

Specifics per doc:
- `SETUP-windows.md`: llama.cpp via official Windows releases (`llama-server.exe`), PowerShell examples, model paths via `$env:LLAMA_DIR` on the user side, firewall note for LAN.
- `SETUP-linux.md`: llama.cpp via distro package/release tarball, `apt install python3 python3-venv`, default `http://127.0.0.1:9931`.
- `SETUP-macos.md`: llama.cpp via Homebrew (`brew install llama.cpp`) or official macOS release, `brew install python`, default localhost.
- `SETUP-hybrid-wsl.md`: llama-server on the Windows host (user installs per `SETUP-windows.md`), MCP server in WSL (`install.sh`); auto gateway detection means `LLAMA_SERVER_URL` usually needs no override; verify with `--health`.
- `SETUP-modular.md`: llama-server on any host reachable over LAN/remote; set `LLAMA_SERVER_URL=http://<host>:<port>` in `config/config.json` or env before starting the MCP server; firewall note; `--health` to verify.

- [ ] **Step 3: Rewrite AGENTS.md** (generalized — drop WSL-specific golden rules, keep frozen model/tool/cache contracts):

```markdown
# AGENTS.md

Guide for AI agents working in this repo.

## What this is

A local **vision MCP server** for any MCP client. `mata-kadalz` (Python, single
file `server.py`) talks to a `llama-server` HTTP endpoint (native on Windows,
Linux, macOS, or in WSL) that runs **Qwen3-VL-4B**.

## Golden rules

- **Never change the model.** Qwen3VL-4B-Instruct-Q4_K_M + mmproj F16 is the
  validated combination. Model/quant changes require re-validation.
- **One tool only:** `vision.inspect(image_path, task)`.
- **Cache contract:** key = sha256(image_sha256 + task + model_id); failed
  requests never cached; inference serialized via `asyncio.Lock`.
- **Never return image bytes** — text JSON only.

## Architecture

```
client -> vision.inspect -> mata-kadalz server.py (stdio or streamable HTTP)
                             -> HTTP POST http://<llama-server>:9931/v1/chat/completions
                             -> llama-server (Qwen3-VL-4B GGUF + mmproj)
```

## Conventions

- Single-file server: `server.py`. stdlib only (`urllib`, `asyncio`, `hashlib`,
  `mimetypes`) plus the `mcp` SDK; `uvicorn` used only for `--transport http`.
- Config precedence: `DEFAULTS` < `config/config.json` (empty skipped) < env.
- Relative config paths resolve against repo root (`BASE_DIR`).
- Host detection: `127.0.0.1` unless WSL, then gateway IP; `LLAMA_SERVER_URL` wins.
- Tests: `pytest` in `tests/`, must not require llama-server running.

## Commands

```bash
.venv/bin/python -m pytest                      # tests (no llama-server needed)
.venv/bin/mata-kadalz --transport stdio          # stdio server
.venv/bin/mata-kadalz --transport http --port 9932  # streamable HTTP server
echo '{"image_path":"/x.png","task":"t"}' | .venv/bin/mata-kadalz --once
```

## References

- `CONTEXT.md` — domain glossary.
- `docs/adr/` — architecture decisions.
```

- [ ] **Step 4: Fill CONTEXT.md glossary** (domain terms):

```markdown
## MCP server
A process exposing tools to MCP clients. Here: `mata-kadalz`, single-file `server.py`.

## llama-server
The HTTP server that actually runs the Qwen3-VL-4B model. Native binary on the
host OS; the MCP server is a thin HTTP client to it.

## vision.inspect
The single tool: analyzes a local image file given a task string, returns
structured JSON. Never returns image bytes.

## Host
The machine running llama-server. WSL auto-detects the Windows host gateway IP.
```

- [ ] **Step 5: Verify docs render / no broken links**

```bash
cd /home/kadalz/dev/mata-kadalz
ls docs/*.md && grep -c "SETUP-" README.md
```

Expected: 5 setup docs exist, README references all 5.

- [ ] **Step 6: Commit**

```bash
cd /home/kadalz/dev/mata-kadalz
git add README.md AGENTS.md CONTEXT.md docs/
git commit -m "docs: per-host setup guides, generalized README/AGENTS, glossary"
```

---

### Task 5: GitHub features — CI, dependabot, issues, release

**Files:**
- Modify: `.github/workflows/ci.yml` (replace template npm CI with uv + pytest; job must produce check context `ci`)
- Modify: `.github/dependabot.yml` (drop npm, add pip for pyproject)
- Create: nothing else in-repo (issues/templates inherited from `.github` org repo)

**Interfaces:**
- Consumes: `pyproject.toml` (uv sync), ruleset `protect-main` (context `ci`)
- Produces: CI green gate on main, dependabot PRs, issue labels, first release

- [ ] **Step 1: Replace CI workflow**

`.github/workflows/ci.yml`:

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:

jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: Set up Python
        run: uv python install 3.12
      - name: Install project + dev deps
        run: uv sync --python 3.12 --group dev
      - name: Run tests
        run: uv run pytest
```

**Important:** the job must be named `ci` so its check context matches the `protect-main` ruleset's required status check.

- [ ] **Step 2: Update dependabot**

`.github/dependabot.yml`:

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

- [ ] **Step 3: Push main so CI runs + ruleset check appears**

```bash
cd /home/kadalz/dev/mata-kadalz
git push -u origin main
```

Expected: push succeeds; GitHub Actions run `ci`; check context `ci` appears on main.

- [ ] **Step 4: Watch CI until green**

```bash
gh run list -R kadalzbaiq/mata-kadalz --workflow ci --limit 1
gh run watch -R kadalzbaiq/mata-kadalz <run-id>
```

Expected: CI passes (pytest green in clean uv env).

- [ ] **Step 5: Create release-1 milestone + tracking issues**

```bash
gh issue create -R kadalzbaiq/mata-kadalz --title "Validate Windows-native setup" --body "Run SETUP-windows.md end-to-end on a clean Windows machine." --label enhancement
gh issue create -R kadalzbaiq/mata-kadalz --title "Validate Linux-native setup" --body "Run SETUP-linux.md end-to-end on a clean Linux machine." --label enhancement
gh issue create -R kadalzbaiq/mata-kadalz --title "Validate macOS setup" --body "Run SETUP-macos.md end-to-end on a clean Mac." --label enhancement
```

- [ ] **Step 6: Create Projects v2 board + add issues**

```bash
gh project create --owner kadalzbaiq --title "mata-kadalz"
# take the printed number N, then:
gh project item-add <N> --owner kadalzbaiq --url <issue1-url>
gh project item-add <N> --owner kadalzbaiq --url <issue2-url>
gh project item-add <N> --owner kadalzbaiq --url <issue3-url>
```

Expected: board exists with 3 items.

- [ ] **Step 7: Create first release (v1.0.0)**

```bash
cd /home/kadalz/dev/mata-kadalz
git fetch --tags origin
gh release create v1.0.0 --title "mata-kadalz v1.0.0" --generate-notes -R kadalzbaiq/mata-kadalz
```

Expected: release page with auto-generated notes.

- [ ] **Step 8: Enable Advanced Security (web UI, manual, once)**

Open `https://github.com/kadalzbaiq/mata-kadalz/settings/security_analysis` →
CodeQL default setup ON, secret scanning push protection ON.
(Public repo free tier; must be done in browser after first push.)

---

### Task 6: Final verification + README release polish

**Files:**
- Verify: whole repo
- Optional: `LICENSE` year/author (template MIT — verify it says kadalzbaiq 2026)

**Interfaces:**
- Consumes: everything
- Produces: shippable main

- [ ] **Step 1: Full local verification**

```bash
cd /home/kadalz/dev/mata-kadalz
.venv/bin/python -m pytest                       # all green
echo '{"image_path":"/tmp/red.png","task":"what color?"}' | .venv/bin/mata-kadalz --once
# expect success:true (needs llama-server running; if not, error code is fine)
.venv/bin/python -m compileall -q server.py && echo "compile OK"
```

- [ ] **Step 2: `--once` cache-hit check (with llama-server up)**

Run same `--once` command twice; second run must show `"cache_hit":true`.

- [ ] **Step 3: Verify LICENSE**

```bash
cd /home/kadalz/dev/mata-kadalz
head -3 LICENSE   # expect "MIT License", copyright kadalzbaiq
```

- [ ] **Step 4: Final commit + push**

```bash
cd /home/kadalz/dev/mata-kadalz
git add -A
git commit -m "chore: release polish"
git push
```

- [ ] **Step 5: Post-push confirmation**

```bash
gh run list -R kadalzbaiq/mata-kadalz --limit 3
gh release view v1.0.0 -R kadalzbaiq/mata-kadalz
```

Expected: CI green on latest commit, release exists.

---

## Self-Review

- **Spec coverage:** dual transport (Task 1), host detection (Task 1), CLI entry (Tasks 1–2), platform detection + connectivity helpers (Task 3), per-host docs (Task 4), GitHub features: ruleset ✓ (already), CI ✓ (Task 5), dependabot ✓ (Task 5), issues/board/release ✓ (Task 5), Advanced Security web UI note ✓ (Task 5), Insights automatic for public ✓ (noted in README), AGENTS/CONTEXT ✓ (Task 4). Spec fully covered. Dependency boundary (llama.cpp/model external, user-installed) enforced across Task 0 seed, Task 3 helpers, Task 4 docs.
- **Placeholder scan:** no TBD/TODO; every step has concrete commands/code.
- **Type consistency:** `_is_wsl()`, `_detect_gateway_ip()`, `_detect_platform()`, `_check_llama_server()`, `_build_server()`, `_parse_args()`, `cli()`, `main()` — names defined in Task 1/3 tests match implementations; `mata-kadalz` console script name consistent across pyproject, README, AGENTS.md, install.sh.
- **Note:** `test_wsl_detection_via_env` asserts `_is_wsl()` True when `WSL_DISTRO_NAME` set — matches implementation. On CI (non-WSL) `_detect_gateway_ip()` returns `127.0.0.1`, so `test_defaults_auto_url` (asserts starts with `http://`) still passes. `--health` on a machine without llama-server exits 1 with `reachable: false` — a valid diagnostic, not a test failure.

## Execution Handoff

After approval, execute via subagent-driven-development (one subagent per task, review between tasks) or inline executing-plans.