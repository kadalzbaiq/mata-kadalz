# Setup: Windows (native)

This guide covers running `mata-kadalz` on Windows. Two parts:

**A. External backend (llama-server + model)** — installed once, by you,
from official sources. `mata-kadalz` only connects to the running server; it
never downloads or bundles these.

**B. mata-kadalz (MCP layer)** — the installable package from this repo.

## A. llama-server + model (external)

1. Install **llama.cpp** following its official docs for Windows:
   https://github.com/ggml-org/llama.cpp#readme (releases:
   https://github.com/ggml-org/llama.cpp/releases) — install the `llama-server.exe`
   binary (CPU build works; use the CUDA/Vulkan build if you have a GPU), do NOT
   install it via this repo.
2. Download the **model** (LLM) from Hugging Face:
   `Qwen3VL-4B-Instruct-Q4_K_M.gguf` —
   https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/Qwen3VL-4B-Instruct-Q4_K_M.gguf
3. Download the **mmproj** (vision encoder):
   `mmproj-Qwen3VL-4B-Instruct-F16.gguf` —
   https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct-GGUF/resolve/main/mmproj-Qwen3VL-4B-Instruct-F16.gguf
   (Place both where your llama.cpp install expects them, e.g. `$env:LLAMA_DIR\models\qwen3-vl-4b`.)
4. Start `llama-server.exe` with your model + mmproj (PowerShell), e.g.:

   ```powershell
   llama-server.exe -m "D:\Software\llama\models\qwen3-vl-4b\Qwen3VL-4B-Instruct-Q4_K_M.gguf" --mmproj "D:\Software\llama\models\qwen3-vl-4b\mmproj-Qwen3VL-4B-Instruct-F16.gguf" --host 0.0.0.0 --port 9931 -c 8192 -t 8 --parallel 1 --image-min-tokens 1024
   ```

   (This is an example for you to run; your exact flags come from llama.cpp docs.)
5. Verify it is healthy: `curl http://localhost:9931/health` → `{"status":"ok"}`.

## B. mata-kadalz (MCP layer)

1. Install Python >=3.11 (https://www.python.org/downloads/windows/).
2. Install the MCP server: `./scripts/install.sh` (Git Bash/WSL) or create a venv manually.
3. Point it at llama-server: the default `http://127.0.0.1:9931` works for the
   common case. Override in `config/config.json` or env `LLAMA_SERVER_URL`
   (see README "Configuration").
4. Confirm connectivity: `.venv/bin/mata-kadalz --health` → `"reachable": true`.
5. Register in your client (stdio or http) — see README "Client registration".
6. Self-check: `echo '{"image_path":"/abs/path/img.png","task":"describe"}' | .venv/bin/mata-kadalz --once`

> Firewall note: if another machine must reach llama-server, allow inbound TCP 9931.