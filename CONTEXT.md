# Repo Context — ubiquitous language

This project's glossary and nothing else. Implementation details, specs, and decisions do NOT belong here.

## Glossary

## mata-kadalz

Lizard Eyes — the MCP layer of this repo: a Python package exposing exactly one vision tool to MCP clients. It never runs inference itself; it proxies to a llama-server HTTP endpoint.

_Avoid_: vision-mcp, lizard-eyes, the server binary

## vision.inspect

The single MCP tool. Takes `image_path` (absolute local path) and `task` (what to analyze), returns structured text JSON. Never returns image bytes.

_Avoid_: vision.ocr, vision.compare, vision.describe_image

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