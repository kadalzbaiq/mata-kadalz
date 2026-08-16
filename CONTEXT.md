# Repo Context — ubiquitous language

This project's glossary and nothing else. Implementation details, specs, and decisions do NOT belong here.

## Glossary

## mata-kadalz

Lizard Eyes — the MCP layer of this repo: a Python package exposing exactly one vision tool to MCP clients. It never runs inference itself; it proxies to a llama-server HTTP endpoint.

_Avoid_: vision-mcp, lizard-eyes, the server binary

## vision.inspect

The single MCP tool. Takes `image_path` (absolute path on the machine where the MCP server runs — the client's machine for stdio, the server's machine for HTTP) and `task` (what to analyze), returns structured text JSON. Never returns image bytes.

_Avoid_: vision.ocr, vision.compare, vision.describe_image

## Image roots

`VISION_IMAGE_ROOTS` restricts which directories `vision.inspect` may read from. Empty (default) = any path; when set, symlink and `..` escapes resolve and are rejected with `IMAGE_PATH_NOT_ALLOWED`. Required hardening for a network-exposed HTTP server.

_Avoid_: allowed dirs, whitelist

## Inference queue

A bounded queue (`VISION_MAX_QUEUE`, default 4) in front of the serialized inference lock. Calls beyond the bound fail fast with `LLAMA_BUSY` instead of piling up. Cancelled requests release the lock and queue slot immediately.

_Avoid_: semaphore, rate limit

## llama-server

External inference runtime from llama.cpp that serves an OpenAI-compatible chat completions endpoint (`/v1/chat/completions`, `/health`). A hard external dependency — the user installs and runs it; this repo never bundles or downloads it.

_Avoid_: llama.cpp server, the backend binary

## GGUF model + mmproj

The validated model combo: `Qwen3VL-4B-Instruct-Q4_K_M.gguf` (LLM) plus `mmproj-Qwen3VL-4B-Instruct-F16.gguf` (vision encoder). Never changed without re-validation.

_Avoid_: qwen model, vision model

## Health check

A CLI probe (`mata-kadalz --health`) that prints platform info, the resolved `LLAMA_SERVER_URL`, and whether llama-server is reachable; exit 0 when reachable.

_Avoid_: health endpoint, ping

## Cache contract

Responses are deduplicated by `sha256(image_sha256 + task + model_id)`. Failed requests are never cached; inference is serialized via a process-wide lock.

_Avoid_: cache, dedup

## Architecture Decisions

See `docs/adr/` for hard-to-reverse decisions. Format: `NNNN-slug.md` (context, choice, reason — 1-3 sentences).