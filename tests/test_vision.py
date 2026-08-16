import asyncio
import json

import pytest

import server


def test_defaults_auto_url():
    cfg = server.load_config()
    assert cfg["LLAMA_SERVER_URL"].startswith("http://")
    assert cfg["VISION_MODEL_ID"] == "qwen3-vl"
    assert int(cfg["VISION_TIMEOUT_SECONDS"]) >= 30


def test_env_override(monkeypatch):
    monkeypatch.setenv("VISION_TIMEOUT_SECONDS", "42")
    monkeypatch.setenv("LLAMA_SERVER_URL", "http://1.2.3.4:9999")
    cfg = server.load_config()
    assert cfg["VISION_TIMEOUT_SECONDS"] == "42"
    assert cfg["LLAMA_SERVER_URL"] == "http://1.2.3.4:9999"


def test_empty_config_value_skipped(monkeypatch, tmp_path):
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"LLAMA_SERVER_URL": "", "VISION_MODEL_ID": "x"}))
    monkeypatch.setattr(server, "CONFIG_FILE", cfg_file)
    cfg = server.load_config()
    assert cfg["LLAMA_SERVER_URL"].startswith("http://")
    assert cfg["VISION_MODEL_ID"] == "x"


def test_relative_paths_resolve_to_repo_root(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    assert server._abs("runtime/vision") == tmp_path / "runtime" / "vision"
    assert server._abs("/abs/path") == __import__("pathlib").Path("/abs/path")


def test_cache_path_deterministic():
    a = server._cache_path("hash1", "task", "qwen3-vl")
    b = server._cache_path("hash1", "task", "qwen3-vl")
    c = server._cache_path("hash1", "task2", "qwen3-vl")
    assert a == b
    assert a != c


def test_error_result_marks_is_error():
    res = server.error_result("IMAGE_NOT_FOUND", "nope")
    assert res.is_error is True
    assert json.loads(res.content[0].text)["error"]["code"] == "IMAGE_NOT_FOUND"


async def _inspect(image_path, task, monkeypatch=None):
    return await server._inspect(image_path, task)


def test_image_not_found(tmp_path):
    async def run():
        res = await server._inspect(tmp_path / "nope.png", "what is this?")
        return res

    res = asyncio.run(run())
    assert res.is_error is True
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_NOT_FOUND"


def test_unsupported_extension(tmp_path):
    p = tmp_path / "file.txt"
    p.write_text("hello")

    async def run():
        return await server._inspect(str(p), "what is this?")

    res = asyncio.run(run())
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_NOT_SUPPORTED"


def test_fake_png_magic_rejected(tmp_path):
    p = tmp_path / "fake.png"
    p.write_bytes(b"not an image")

    async def run():
        return await server._inspect(str(p), "what is this?")

    res = asyncio.run(run())
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_NOT_SUPPORTED"


def test_cache_hit_returns_without_llama(tmp_path, monkeypatch):
    img = tmp_path / "real.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"payload")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(server, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)

    data = img.read_bytes()
    h = server._sha256(data)
    cache_file = server._cache_path(h, "task", "qwen3-vl")
    cache_file.write_text(json.dumps({"success": True, "summary": "cached answer"}))

    called = {"n": 0}

    async def boom(*a, **k):
        called["n"] += 1
        return None, None

    monkeypatch.setattr(server, "_call_llama", boom)

    async def run():
        return await server._inspect(str(img), "task")

    res = asyncio.run(run())
    body = json.loads(res.content[0].text)
    assert body["cache_hit"] is True
    assert called["n"] == 0


def test_unknown_tool():
    async def run():
        return await server._on_call_tool(
            None,
            __import__(
                "mcp.types", fromlist=["CallToolRequestParams"]
            ).CallToolRequestParams(name="nope", arguments={}),
        )

    res = asyncio.run(run())
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "UNKNOWN_TOOL"
