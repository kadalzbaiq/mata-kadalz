# Setup: WSL2 on Windows (hybrid)

This guide covers running `mata-kadalz` when your MCP client lives in WSL2 but
llama-server runs on the Windows host (native). Two parts:

**A. External backend (llama-server + model)** — installed once on Windows,
by you, from official sources. `mata-kadalz` only connects to the running
server; it never downloads or bundles these.

**B. mata-kadalz (MCP layer)** — the installable package from this repo, run
inside WSL.

## A. llama-server + model (external, on the Windows host)

Install llama.cpp, the model, and the mmproj on Windows exactly as described
in `SETUP-windows.md` (sections A.1–A.5). Start `llama-server.exe` bound to
`--host 0.0.0.0` so WSL can reach it.

## B. mata-kadalz (MCP layer, in WSL)

1. Install Python >=3.11 inside WSL: `sudo apt install python3 python3-venv`.
2. Install the MCP server: `./scripts/install.sh` (creates `.venv`, installs the `mata-kadalz` package only).
3. Point it at llama-server: `mata-kadalz` auto-detects the WSL gateway IP
   (the Windows host) and defaults to `http://<gateway-ip>:9931`, so no
   override is usually needed. If detection is wrong **or fails** (gateway
   detection needs `ip route` to report a default route), set `LLAMA_SERVER_URL`
   explicitly in `config/config.json` or env — without it, calls return
   `LLAMA_SERVER_URL_NOT_SET` and `--health` shows the missing URL.
4. Confirm connectivity: `.venv/bin/mata-kadalz --health` → `"reachable": true`.
5. Register in your client (stdio or http) — see README "Client registration".
6. Self-check: `echo '{"image_path":"/abs/path/img.png","task":"describe"}' | .venv/bin/mata-kadalz --once`

> Firewall note: Windows Defender Firewall may block inbound traffic from WSL.
> If `--health` shows unreachable, allow inbound TCP 9931 for llama-server.exe.