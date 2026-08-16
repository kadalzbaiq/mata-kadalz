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
- **Dependency boundary:** `mata-kadalz` is the MCP layer only. Never vendor,
  bundle, download, or manage llama.cpp/model files in this repo. The docs
  point users to official llama.cpp/Hugging Face sources; the package only
  connects to an already-running llama-server.

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
- Logging: file handler into `<runtime>/vision/logs/vision-mcp.log`.
- Commit style: Conventional Commits, matching `git log`.

## Commands

```bash
.venv/bin/python -m pytest                      # tests (no llama-server needed)
.venv/bin/mata-kadalz --health                  # print platform + llama-server health
.venv/bin/mata-kadalz --transport stdio          # stdio server
.venv/bin/mata-kadalz --transport http --port 9932  # streamable HTTP server
echo '{"image_path":"/x.png","task":"t"}' | .venv/bin/mata-kadalz --once
```

## References

- `CONTEXT.md` — domain glossary.
- `docs/adr/` — architecture decisions.