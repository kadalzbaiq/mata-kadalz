import argparse
import asyncio
import io
import json
import os
import sys
import threading
import time
import urllib.error

import httpx2 as httpx
import pytest

from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client

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


def test_detect_platform_shape():
    p = server._detect_platform()
    assert set(p) == {"os", "arch", "wsl"}
    assert p["os"] in {"linux", "darwin", "windows"}
    assert isinstance(p["wsl"], bool)


def test_check_llama_server_ok(monkeypatch):
    class FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

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


def _make_png(path):
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"payload")
    return path


def _ok_llama(*a, **k):
    return {"choices": [{"message": {"content": "ok"}}], "usage": {}}, None


def _inspect_success(monkeypatch, tmp_path, img):
    monkeypatch.setattr(server, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)
    monkeypatch.setattr(server, "_call_llama", _ok_llama)


# ---- P1#1 filesystem / image-root policy ----


def test_image_roots_allows_inside(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    img = _make_png(root / "real.png")
    monkeypatch.setattr(server, "_IMAGE_ROOTS", [root.resolve()])
    _inspect_success(monkeypatch, tmp_path, img)
    res = asyncio.run(server._inspect(str(img), "task"))
    assert json.loads(res.content[0].text)["success"] is True


def test_image_roots_rejects_outside(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    img = _make_png(tmp_path / "outside.png")
    monkeypatch.setattr(server, "_IMAGE_ROOTS", [root.resolve()])
    res = asyncio.run(server._inspect(str(img), "task"))
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_PATH_NOT_ALLOWED"


def test_image_roots_rejects_dotdot_escape(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    _make_png(tmp_path / "secret.png")
    monkeypatch.setattr(server, "_IMAGE_ROOTS", [root.resolve()])
    path = str(root / ".." / "secret.png")
    res = asyncio.run(server._inspect(path, "task"))
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_PATH_NOT_ALLOWED"


def test_image_roots_rejects_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    secret = _make_png(tmp_path / "secret.png")
    link = root / "link.png"
    os.symlink(secret, link)
    monkeypatch.setattr(server, "_IMAGE_ROOTS", [root.resolve()])
    res = asyncio.run(server._inspect(str(link), "task"))
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_PATH_NOT_ALLOWED"


def test_image_roots_nonexistent_inside_root(tmp_path, monkeypatch):
    root = tmp_path / "allowed"
    root.mkdir()
    monkeypatch.setattr(server, "_IMAGE_ROOTS", [root.resolve()])
    res = asyncio.run(server._inspect(str(root / "nope.png"), "task"))
    body = json.loads(res.content[0].text)
    assert body["error"]["code"] == "IMAGE_NOT_FOUND"


def test_image_roots_unrestricted_by_default(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    monkeypatch.setattr(server, "_IMAGE_ROOTS", [])
    _inspect_success(monkeypatch, tmp_path, img)
    res = asyncio.run(server._inspect(str(img), "task"))
    assert json.loads(res.content[0].text)["success"] is True


# ---- P1#2 system prompt ----


def test_chat_body_includes_system_prompt():
    body = server._build_chat_body(b"img", "image/png", "what color?")
    assert body["messages"][0] == {"role": "system", "content": server.SYSTEM_PROMPT}
    user = body["messages"][1]
    assert user["role"] == "user"
    assert user["content"][0]["type"] == "image_url"
    assert user["content"][1]["text"] == "what color?"


# ---- P1#3 cancellation ----


def test_cancellation_releases_lock_and_skips_cache(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(server, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)
    gate = asyncio.Event()

    async def fake_to_thread(fn, *a, **k):
        await gate.wait()
        return None, None

    monkeypatch.setattr(server.asyncio, "to_thread", fake_to_thread)

    async def run():
        task = asyncio.create_task(server._inspect(str(img), "task"))
        for _ in range(200):
            if server._LOCK.locked():
                break
            await asyncio.sleep(0.005)
        assert server._LOCK.locked()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not server._LOCK.locked()
        assert list(cache_dir.iterdir()) == []

    asyncio.run(run())


# ---- P1#5 --once exit codes ----


def _once_result(monkeypatch, capsys, line_bytes, inspect_override=None):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(line_bytes)))
    args = argparse.Namespace(
        transport="stdio",
        host="127.0.0.1",
        port=9932,
        path="/mcp",
        once=True,
        health=False,
    )
    monkeypatch.setattr(server, "_parse_args", lambda argv=None: args)
    if inspect_override is not None:
        monkeypatch.setattr(server, "_inspect", inspect_override)
    with pytest.raises(SystemExit) as ei:
        asyncio.run(server.main())
    return ei.value.code, json.loads(capsys.readouterr().out)


def test_once_exit_success(tmp_path, monkeypatch, capsys):
    img = _make_png(tmp_path / "real.png")
    _inspect_success(monkeypatch, tmp_path, img)
    line = json.dumps({"image_path": str(img), "task": "t"}).encode()
    code, body = _once_result(monkeypatch, capsys, line)
    assert code == 0
    assert body["success"] is True


def test_once_exit_cache_hit(tmp_path, monkeypatch, capsys):
    img = _make_png(tmp_path / "real.png")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(server, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)
    cache_file = server._cache_path(
        server._sha256(img.read_bytes()), "task", "qwen3-vl"
    )
    cache_file.write_text(json.dumps({"success": True, "summary": "cached"}))

    def boom(*a, **k):
        raise AssertionError("llama should not be called on cache hit")

    monkeypatch.setattr(server, "_call_llama", boom)
    line = json.dumps({"image_path": str(img), "task": "task"}).encode()
    code, body = _once_result(monkeypatch, capsys, line)
    assert code == 0
    assert body["cache_hit"] is True


def test_once_exit_llama_unavailable(tmp_path, monkeypatch, capsys):
    img = _make_png(tmp_path / "real.png")
    _inspect_success(monkeypatch, tmp_path, img)
    monkeypatch.setattr(
        server,
        "_call_llama",
        lambda *a, **k: (
            None,
            server.error_result("LLAMA_SERVER_UNAVAILABLE", "refused"),
        ),
    )
    line = json.dumps({"image_path": str(img), "task": "t"}).encode()
    code, body = _once_result(monkeypatch, capsys, line)
    assert code == 1
    assert body["error"]["code"] == "LLAMA_SERVER_UNAVAILABLE"


def test_once_exit_invalid_image(tmp_path, monkeypatch, capsys):
    line = json.dumps({"image_path": str(tmp_path / "nope.png"), "task": "t"}).encode()
    code, body = _once_result(monkeypatch, capsys, line)
    assert code == 1
    assert body["error"]["code"] == "IMAGE_NOT_FOUND"


def test_once_exit_malformed_input(monkeypatch, capsys):
    code, body = _once_result(monkeypatch, capsys, b"not json")
    assert code == 1
    assert body["error"]["code"] == "INVALID_ARGUMENTS"


# ---- P2#6 WSL gateway ----


def test_wsl_gateway_found(monkeypatch):
    monkeypatch.setattr(server, "_is_wsl", lambda: True)

    class R:
        stdout = "default via 192.168.64.1 dev eth0 proto kernel\n"

    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: R())
    assert server._detect_gateway_ip() == "192.168.64.1"


def test_wsl_gateway_missing_returns_none(monkeypatch):
    monkeypatch.setattr(server, "_is_wsl", lambda: True)

    class R:
        stdout = ""

    monkeypatch.setattr(server.subprocess, "run", lambda *a, **k: R())
    assert server._detect_gateway_ip() is None


def test_wsl_no_gateway_requires_explicit_url(monkeypatch):
    monkeypatch.setattr(server, "DEFAULTS", dict(server.DEFAULTS))
    server.DEFAULTS["LLAMA_SERVER_URL"] = ""
    cfg = server.load_config()
    assert cfg["LLAMA_SERVER_URL"] == ""


def test_empty_server_url_gives_clear_error(monkeypatch):
    monkeypatch.setattr(server, "_SERVER_URL", "")
    res, err = server._call_llama(b"x", "image/png", "t")
    assert res is None
    body = json.loads(err.content[0].text)
    assert body["error"]["code"] == "LLAMA_SERVER_URL_NOT_SET"


# ---- P2#7 model-aware cache ----


def test_cache_path_distinguishes_model():
    a = server._cache_path("hash", "task", "qwen3-vl")
    b = server._cache_path("hash", "task", "qwen3-vl-2")
    assert a != b


def test_model_change_invalidates_cache(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(server, "_CACHE_DIR", cache_dir)
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl-2")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)
    cache_file = server._cache_path(
        server._sha256(img.read_bytes()), "task", "qwen3-vl"
    )
    cache_file.write_text(json.dumps({"success": True, "summary": "cached"}))
    called = {"n": 0}

    def fake_call(*a, **k):
        called["n"] += 1
        return _ok_llama()

    monkeypatch.setattr(server, "_call_llama", fake_call)
    res = asyncio.run(server._inspect(str(img), "task"))
    body = json.loads(res.content[0].text)
    assert body["cache_hit"] is False
    assert called["n"] == 1


# ---- P2#8 concurrency / bounded queue ----


def test_inference_serialized_one_active(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    _inspect_success(monkeypatch, tmp_path, img)
    monkeypatch.setattr(server, "_MAX_QUEUE", 8)
    monkeypatch.setattr(server, "_QUEUE_COUNT", 0)
    sl = threading.Lock()
    state = {"active": 0, "max": 0}

    def fake_call(image_data, mime, task):
        with sl:
            state["active"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.15)
        with sl:
            state["active"] -= 1
        return {"choices": [{"message": {"content": task}}], "usage": {}}, None

    monkeypatch.setattr(server, "_call_llama", fake_call)

    async def run():
        await asyncio.gather(*[server._inspect(str(img), f"task{i}") for i in range(3)])

    asyncio.run(run())
    assert state["max"] == 1


def test_queue_full_returns_busy(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    monkeypatch.setattr(server, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)
    monkeypatch.setattr(server, "_MAX_QUEUE", 1)
    monkeypatch.setattr(server, "_QUEUE_COUNT", 0)
    gate = asyncio.Event()

    async def fake_to_thread(fn, *a, **k):
        await gate.wait()
        return _ok_llama()

    monkeypatch.setattr(server.asyncio, "to_thread", fake_to_thread)

    async def run():
        t1 = asyncio.create_task(server._inspect(str(img), "taskA"))
        for _ in range(200):
            if server._LOCK.locked():
                break
            await asyncio.sleep(0.005)
        assert server._LOCK.locked()
        res2 = await server._inspect(str(img), "taskB")
        body = json.loads(res2.content[0].text)
        assert body["error"]["code"] == "LLAMA_BUSY"
        gate.set()
        r1 = await t1
        assert json.loads(r1.content[0].text)["success"] is True

    asyncio.run(run())


# ---- P3 HTTP integration (real uvicorn server) ----


def _make_app():
    return server._build_server().streamable_http_app(streamable_http_path="/mcp")


def _with_http_server(fn):
    import socket

    import uvicorn

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    app = _make_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    uvs = uvicorn.Server(config)
    t = threading.Thread(target=uvs.run, daemon=True)
    t.start()
    deadline = time.time() + 15
    while time.time() < deadline and not uvs.started:
        time.sleep(0.05)
    assert uvs.started, "uvicorn did not start"
    try:
        return asyncio.run(_http_session(f"http://127.0.0.1:{port}/mcp", fn))
    finally:
        uvs.should_exit = True
        t.join(timeout=5)


async def _http_session(url, fn):
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await fn(session)


def test_http_tool_discovery():
    async def fn(session):
        tools = await session.list_tools()
        return [t.name for t in tools.tools]

    names = _with_http_server(fn)
    assert "vision.inspect" in names


def test_http_tool_invocation(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    _inspect_success(monkeypatch, tmp_path, img)

    async def fn(session):
        res = await session.call_tool(
            "vision.inspect", {"image_path": str(img), "task": "t"}
        )
        return json.loads(res.content[0].text)

    body = _with_http_server(fn)
    assert body["success"] is True


def test_http_invalid_request(tmp_path):
    async def fn(session):
        res = await session.call_tool(
            "vision.inspect", {"image_path": str(tmp_path / "nope.png")}
        )
        return json.loads(res.content[0].text)

    body = _with_http_server(fn)
    assert body["error"]["code"] == "INVALID_ARGUMENTS"


def test_http_unknown_tool():
    async def fn(session):
        res = await session.call_tool("nope", {})
        return json.loads(res.content[0].text)

    body = _with_http_server(fn)
    assert body["error"]["code"] == "UNKNOWN_TOOL"


def test_http_long_running(tmp_path, monkeypatch):
    img = _make_png(tmp_path / "real.png")
    monkeypatch.setattr(server, "_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(server, "_MODEL_ID", "qwen3-vl")
    monkeypatch.setattr(server, "_MAX_IMAGE", 10_000_000)
    block = threading.Event()

    def fake_call(image_data, mime, task):
        block.wait(5)
        return _ok_llama()

    monkeypatch.setattr(server, "_call_llama", fake_call)

    async def fn(session):
        call = asyncio.create_task(
            session.call_tool("vision.inspect", {"image_path": str(img), "task": "t"})
        )
        for _ in range(200):
            if server._LOCK.locked():
                break
            await asyncio.sleep(0.005)
        assert server._LOCK.locked()
        block.set()
        res = await call
        return json.loads(res.content[0].text)

    body = _with_http_server(fn)
    assert body["success"] is True
