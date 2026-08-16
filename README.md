# mata-kadalz 🦎

Lizard Eyes — local **vision MCP server** backed by **Qwen3-VL-4B** running on `llama-server`.
Gives any MCP client (opencode, Claude, Codex, ...) one tool: `vision.inspect(image_path, task)`.

```
client -> vision.inspect -> mata-kadalz server.py (stdio or streamable HTTP)
                            -> HTTP POST http://<llama-server>:9931/v1/chat/completions
                            -> llama-server (Qwen3-VL-4B GGUF + mmproj)
```

`mata-kadalz` is a thin MCP layer. The inference runtime (`llama-server` from llama.cpp) and the
model are **external dependencies you install yourself**; this repo never downloads or bundles them.

## Quick start

> **Install from source.** This project is not yet published to PyPI, so the package is
> installed from this repository (see [Setup guides](#supported-setups) for your platform).

1. Install Python **>= 3.11**.
2. Install **llama-server** (llama.cpp) and the **Qwen3-VL-4B** model + mmproj — external,
   from official sources (links in the [Model](#model) and [Setup guides](#supported-setups) sections).
3. Start `llama-server` and confirm it is healthy: `curl http://localhost:9931/health` → `{"status":"ok"}`.
4. Install `mata-kadalz` from this repo into a venv:
   ```bash
   git clone https://github.com/kadalzbaiq/mata-kadalz.git
   cd mata-kadalz
   bash scripts/install.sh          # POSIX (Linux/macOS/WSL); Windows: see docs/SETUP-windows.md
   ```
5. Confirm the MCP server can reach llama-server: `.venv/bin/mata-kadalz --health`.
6. Register `mata-kadalz` in your MCP client — see [Client registration](#client-registration).

## Supported setups

| Host | llama-server runs on | Setup doc |
|---|---|---|
| Windows (native) | Windows | [docs/SETUP-windows.md](docs/SETUP-windows.md) |
| Linux (native) | Linux | [docs/SETUP-linux.md](docs/SETUP-linux.md) |
| macOS (native) | macOS | [docs/SETUP-macos.md](docs/SETUP-macos.md) |
| WSL2 on Windows | Windows host (native) | [docs/SETUP-hybrid-wsl.md](docs/SETUP-hybrid-wsl.md) |
| Any / remote / custom | anywhere reachable over HTTP | [docs/SETUP-modular.md](docs/SETUP-modular.md) |

## Model

- Model: `Qwen3VL-4B-Instruct-Q4_K_M.gguf` (LLM, ~2.5 GB)
- Vision encoder: `mmproj-Qwen3VL-4B-Instruct-F16.gguf` (~800 MB)
- Source: `Qwen/Qwen3-VL-4B-Instruct-GGUF`
  - https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/Qwen3VL-4B-Instruct-Q4_K_M.gguf
  - https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-4B-Instruct-F16.gguf

Do not change the quant or mmproj combo without re-validating; this is the verified working setup.

## Layout

```
server.py                 # MCP server (stdio + streamable HTTP), single file
config/config.json        # optional overrides (empty = auto)
scripts/install.sh        # install the mata-kadalz package only
docs/                     # per-host setup guides
tests/                    # pytest (no llama-server needed)
runtime/                  # logs + image cache (gitignored)
```

## Client registration

Replace `/path/to/mata-kadalz/.venv/bin/mata-kadalz` with the real path on your machine.

stdio (local — same machine as the images):

```bash
# claude
claude mcp add vision -- /path/to/mata-kadalz/.venv/bin/mata-kadalz
# codex
codex mcp add vision -- /path/to/mata-kadalz/.venv/bin/mata-kadalz
```

streamable HTTP (remote — server machine may differ from client):

```bash
# claude
claude mcp add --transport http vision http://127.0.0.1:9932/mcp
# codex
codex mcp add vision --url http://127.0.0.1:9932/mcp
```

opencode (config in `opencode.json`):

```jsonc
{
  "mcp": {
    "vision": {
      "type": "local",                 // stdio
      "command": ["/path/to/mata-kadalz/.venv/bin/mata-kadalz"]
    }
    // or "type": "remote", "url": "http://127.0.0.1:9932/mcp"  // streamable HTTP
  }
}
```

## Usage

One tool: **`vision.inspect`** — takes `image_path` (absolute path on the machine where the MCP server runs) and `task` (what to analyze). Returns structured JSON:

```json
{ "success": true, "summary": "...", "details": "", "warnings": [], "cache_hit": true }
```

On failure it returns `is_error: true` with a machine-readable code, e.g. `IMAGE_NOT_FOUND`, `IMAGE_NOT_SUPPORTED`, `IMAGE_PATH_NOT_ALLOWED`, `LLAMA_SERVER_URL_NOT_SET`, `LLAMA_SERVER_TIMEOUT`, `LLAMA_BUSY`, `INVALID_VISION_RESPONSE`.

The server also embeds a **system prompt** (`SYSTEM_PROMPT`) instructing the vision model how to structure its output; the prompt is sent on every inference request.

### HTTP vs stdio — where files must live

- **stdio (local):** the MCP client and the server share one machine, so `image_path` is a path on that machine.
- **streamable HTTP (remote):** the client and the server may be on different machines — `image_path` is resolved **on the server machine**, not the client's. Set `VISION_IMAGE_ROOTS` to restrict which directories the server will read from (strongly recommended for a network-exposed server).

### Security for HTTP deployments

If you expose the server over the network:

- **Set `VISION_IMAGE_ROOTS`** so the server can only read from the directories you choose. With it unset, the server can read any path on the host.
- **Bind to a safe interface.** `--host 127.0.0.1` (the default) only accepts local connections. For LAN/remote access, prefer a VPN or a firewall rule over binding `0.0.0.0` on a public interface.
- **No authentication is built in.** Put the endpoint behind an authenticated reverse proxy or your VPN. The HTTP transport speaks raw MCP; there is no token/user layer.
- Allow inbound traffic only on the ports you use: **9931** (llama-server) and **9932** (mata-kadalz HTTP transport).

## Configuration

Config precedence: `DEFAULTS` < `config/config.json` (empty values skipped) < environment variables.

| Key | Default | Notes |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://<gateway-ip>:9931` | Auto-detects WSL gateway IP; set explicitly to override. If WSL gateway detection fails and no URL is set, inference returns `LLAMA_SERVER_URL_NOT_SET` |
| `VISION_RUNTIME_DIR` | `<repo>/runtime/vision` | Relative paths resolve against repo root |
| `VISION_CACHE_DIR` | `<repo>/runtime/vision/cache` | |
| `VISION_LOG_DIR` | `<repo>/runtime/vision/logs` | |
| `VISION_TIMEOUT_SECONDS` | `180` | CPU inference takes 10–130 s per call |
| `VISION_MAX_IMAGE_SIZE` | `20971520` | 20 MB |
| `VISION_MODEL_ID` | `qwen3-vl` | |
| `VISION_IMAGE_ROOTS` | *(empty = any path)* | Restrict readable image dirs. JSON array or comma-separated, relative to repo root. Symlinks and `..` escapes resolve and are rejected |
| `VISION_MAX_QUEUE` | `4` | Bounded inference queue; beyond this, calls fail fast with `LLAMA_BUSY` |

Example override in `config/config.json`:

```json
{ "LLAMA_SERVER_URL": "http://192.168.64.1:9931" }
```

Restrict a network-exposed server to one directory:

```json
{ "VISION_IMAGE_ROOTS": ["/srv/shared-images"] }
```

## Health check

Confirm the MCP can reach llama-server before wiring up a client:

```bash
.venv/bin/mata-kadalz --health
```

Prints platform, resolved `LLAMA_SERVER_URL`, and a `reachable: true/false` health probe; exits 0 when reachable.

## Caching

Requests are deduplicated by `sha256(image) + task + model`. A cache hit returns instantly without touching llama-server. Failed requests are never cached. Inference is serialized with a process-wide lock (one concurrent call at a time); the queue beyond the lock is bounded by `VISION_MAX_QUEUE` and returns `LLAMA_BUSY` when full.

**Cache invalidation:** changing `VISION_MODEL_ID` invalidates the cache automatically, because the model id is part of the cache key — stale answers from an older model are never served.

**Cancellation:** if the MCP client cancels a request mid-inference, the server releases its lock and queue slot immediately, discards the in-flight result (never caches a partial one), and the error propagates without crashing the server. The underlying llama-server call keeps running in the background; its result is ignored.

## Self-check

```bash
echo '{"image_path":"/path/to/img.png","task":"describe"}' | .venv/bin/mata-kadalz --once
```

Reads one JSON request from stdin, runs it, prints the result, and exits: **0** on success or cache hit, **1** on any error (invalid input, missing file, unreachable llama-server, ...). Useful for scripting and cron-style smoke checks.

## Test

```bash
.venv/bin/python -m pytest
```

No llama-server required — tests cover config, file validation, magic bytes, cache logic, image-root policy, cancellation, `--once` exit codes, WSL gateway detection, bounded queue, and a real streamable-HTTP session over uvicorn.

## HTTP transport dependency

`uvicorn` is only needed for `--transport http`. It already ships transitively with the MCP SDK, but it is also declared as an explicit optional extra so the intent is unambiguous:

```bash
# from a source checkout (until PyPI publication)
pip install -e '.[http]'          # or: bash scripts/install.sh then pip install -e '.[http]'
```

> Until the package is published to PyPI, `pip install mata-kadalz` and
> `pip install 'mata-kadalz[http]'` will **not** work. Use a source checkout.

## License

[MIT](LICENSE)