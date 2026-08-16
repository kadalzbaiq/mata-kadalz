# Setup: Any / remote / custom

This guide covers running `mata-kadalz` when llama-server runs on any machine
reachable over the network (LAN, remote box, container, ...). Two parts:

**A. External backend (llama-server + model)** — installed once on the host
that runs it, by you, from official sources. `mata-kadalz` only connects to
the running server; it never downloads or bundles these.

**B. mata-kadalz (MCP layer)** — the installable package from this repo.

## A. llama-server + model (external)

1. Install **llama.cpp** on the host following its official docs:
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
4. Start `llama-server` bound to an interface reachable from the MCP host,
   e.g.:

   ```bash
   llama-server -m Qwen3VL-4B-Instruct-Q4_K_M.gguf --mmproj mmproj-Qwen3VL-4B-Instruct-F16.gguf \
     --host 0.0.0.0 --port 9931 -c 8192 -t 8 --parallel 1 --image-min-tokens 1024
   ```

   (This is an example for you to run; your exact flags come from llama.cpp docs.)
5. Verify it is healthy from the MCP host:
   `curl http://<llama-host>:9931/health` → `{"status":"ok"}`.

## B. mata-kadalz (MCP layer)

1. Install Python >=3.11 on the MCP host.
2. Install the MCP server: `./scripts/install.sh` (creates `.venv`, installs the `mata-kadalz` package only).
3. Point it at llama-server: set `LLAMA_SERVER_URL=http://<llama-host>:<port>`
   in `config/config.json` or as an env var **before** starting the MCP
   server. Example:

   ```json
   { "LLAMA_SERVER_URL": "http://192.168.1.50:9931" }
   ```

4. Confirm connectivity: `.venv/bin/mata-kadalz --health` → `"reachable": true`.
5. Register in your client (stdio or http) — see README "Client registration".
6. Self-check: `echo '{"image_path":"/abs/path/img.png","task":"describe"}' | .venv/bin/mata-kadalz --once`

> Firewall note: allow inbound TCP `<port>` (9931) on the llama-server host
> for the MCP host's IP.
> If you use the streamable HTTP transport remotely, bind it carefully
> (`--host 0.0.0.0 --port 9932`) and keep it behind a firewall/VPN — it
> exposes the MCP tool to the network.