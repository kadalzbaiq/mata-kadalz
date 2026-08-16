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

## Supported setups

| Host | llama-server runs on | Setup doc |
|---|---|---|
| Windows only | Windows (native) | `docs/SETUP-windows.md` |
| Linux only | Linux (native) | `docs/SETUP-linux.md` |
| macOS only | macOS (native) | `docs/SETUP-macos.md` |
| WSL2 on Windows | Windows host (native) | `docs/SETUP-hybrid-wsl.md` |
| Any / remote / custom | anywhere reachable over HTTP | `docs/SETUP-modular.md` |

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

## Usage

One tool: **`vision.inspect`** — takes `image_path` (absolute path on this machine) and `task` (what to analyze). Returns structured JSON:

```json
{ "success": true, "summary": "...", "details": "", "warnings": [], "cache_hit": true }
```

On failure it returns `is_error: true` with a machine-readable code, e.g. `IMAGE_NOT_FOUND`, `IMAGE_NOT_SUPPORTED`, `LLAMA_SERVER_TIMEOUT`, `INVALID_VISION_RESPONSE`.

## Configuration

Config precedence: `DEFAULTS` < `config/config.json` (empty values skipped) < environment variables.

| Key | Default | Notes |
|---|---|---|
| `LLAMA_SERVER_URL` | `http://<gateway-ip>:9931` | Auto-detects WSL gateway IP; set explicitly to override |
| `VISION_RUNTIME_DIR` | `<repo>/runtime/vision` | Relative paths resolve against repo root |
| `VISION_CACHE_DIR` | `<repo>/runtime/vision/cache` | |
| `VISION_LOG_DIR` | `<repo>/runtime/vision/logs` | |
| `VISION_TIMEOUT_SECONDS` | `180` | CPU inference takes 10–130 s per call |
| `VISION_MAX_IMAGE_SIZE` | `20971520` | 20 MB |
| `VISION_MODEL_ID` | `qwen3-vl` | |

Example override in `config/config.json`:

```json
{ "LLAMA_SERVER_URL": "http://192.168.64.1:9931" }
```

## Health check

Confirm the MCP can reach llama-server before wiring up a client:

```bash
.venv/bin/mata-kadalz --health
```

Prints platform, resolved `LLAMA_SERVER_URL`, and a `reachable: true/false` health probe; exits 0 when reachable.

## Caching

Requests are deduplicated by `sha256(image) + task + model`. A cache hit returns instantly without touching llama-server. Failed requests are never cached. Inference is serialized with a process-wide lock (one concurrent call at a time).

## Self-check

```bash
echo '{"image_path":"/path/to/img.png","task":"describe"}' | .venv/bin/mata-kadalz --once
```

## Test

```bash
.venv/bin/python -m pytest
```

No llama-server required — tests cover config, file validation, magic bytes, cache logic, and error codes.

## License

[MIT](LICENSE)