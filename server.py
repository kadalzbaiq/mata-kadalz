import argparse
import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    TextContent,
    Tool,
)

BASE_DIR = Path(__file__).resolve().parent
SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".tif"}
MAGIC = {
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"\xff\xd8\xff": "image/jpeg",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",
    b"BM": "image/bmp",
    b"II*\x00": "image/tiff",
    b"MM\x00*": "image/tiff",
}
SYSTEM_PROMPT = (
    "You are a vision assistant for a coding/automation agent. "
    "Analyze the image according to the task. "
    "Only report information that is visibly supported by the image. "
    "Do not invent or guess missing values. "
    "Prefer concise, precise findings."
)

log = logging.getLogger("vision_mcp")


def _is_wsl():
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    if platform.system() != "Linux":
        return False
    try:
        with open("/proc/version", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except Exception:
        return False


def _detect_gateway_ip():
    if not _is_wsl():
        return "127.0.0.1"
    try:
        out = subprocess.run(
            ["ip", "route"], capture_output=True, text=True, timeout=5
        ).stdout
        for line in out.splitlines():
            if line.startswith("default"):
                return line.split()[2]
    except Exception:
        pass
    return "127.0.0.1"


DEFAULTS = {
    "LLAMA_SERVER_URL": f"http://{_detect_gateway_ip()}:9931",
    "VISION_RUNTIME_DIR": str(BASE_DIR / "runtime" / "vision"),
    "VISION_CACHE_DIR": str(BASE_DIR / "runtime" / "vision" / "cache"),
    "VISION_LOG_DIR": str(BASE_DIR / "runtime" / "vision" / "logs"),
    "VISION_TIMEOUT_SECONDS": "180",
    "VISION_MAX_IMAGE_SIZE": "20971520",
    "VISION_MODEL_ID": "qwen3-vl",
}
CONFIG_FILE = BASE_DIR / "config" / "config.json"


def load_config():
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                for k, v in json.load(f).items():
                    if v:
                        cfg[k] = v
        except Exception as e:
            log.warning("could not read config file %s: %s", CONFIG_FILE, e)
    for k in DEFAULTS:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


CONFIG = load_config()


def _abs(path):
    p = Path(path)
    return p if p.is_absolute() else (BASE_DIR / p)


_RUNTIME_DIR = _abs(CONFIG["VISION_RUNTIME_DIR"])
_CACHE_DIR = _abs(CONFIG["VISION_CACHE_DIR"])
_LOG_DIR = _abs(CONFIG["VISION_LOG_DIR"])
_TIMEOUT = float(CONFIG["VISION_TIMEOUT_SECONDS"])
_MAX_IMAGE = int(CONFIG["VISION_MAX_IMAGE_SIZE"])
_SERVER_URL = CONFIG["LLAMA_SERVER_URL"].rstrip("/")
_MODEL_ID = CONFIG["VISION_MODEL_ID"]
_LOCK = asyncio.Lock()


def setup_logging():
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(_LOG_DIR / "vision-mcp.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


def error_result(code, message):
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=json.dumps(
                    {
                        "success": False,
                        "error": {"code": code, "message": message},
                        "cache_hit": False,
                    }
                ),
            )
        ],
        is_error=True,
    )


def _read_image(path):
    try:
        data = path.read_bytes()
    except Exception as e:
        return None, error_result("IMAGE_READ_ERROR", f"cannot read image file: {e}")
    if not data:
        return None, error_result("IMAGE_READ_ERROR", "image file is empty")
    if len(data) > _MAX_IMAGE:
        return None, error_result(
            "IMAGE_NOT_SUPPORTED",
            f"image exceeds size limit ({len(data)} > {_MAX_IMAGE} bytes)",
        )
    return data, None


def _sha256(b):
    return hashlib.sha256(b).hexdigest()


def _cache_path(image_hash, task, model):
    key = hashlib.sha256(f"{image_hash}|{task}|{model}".encode()).hexdigest()
    return _CACHE_DIR / f"{key}.json"


def _read_cache(cache_file):
    try:
        if not cache_file.exists():
            return None
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning("cache read error %s: %s", cache_file, e)
        return None


def _write_cache(cache_file, payload):
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except Exception as e:
        log.warning("cache write error %s: %s", cache_file, e)
        return False


def _call_llama(image_data, mime, task):
    body = {
        "model": _MODEL_ID,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:"
                            + mime
                            + ";base64,"
                            + base64.b64encode(image_data).decode("ascii")
                        },
                    },
                    {"type": "text", "text": task},
                ],
            }
        ],
        "max_tokens": 512,
        "temperature": 0.2,
        "stream": False,
    }
    req = urllib.request.Request(
        f"{_SERVER_URL}/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return None, error_result(
            "LLAMA_SERVER_ERROR",
            f"llama-server HTTP {e.code}: {e.read().decode()[:300]}",
        )
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", str(e))
        if isinstance(reason, TimeoutError):
            return None, error_result(
                "LLAMA_SERVER_TIMEOUT", f"llama-server timed out after {_TIMEOUT}s"
            )
        return None, error_result(
            "LLAMA_SERVER_UNAVAILABLE", f"cannot reach llama-server: {reason}"
        )
    except TimeoutError:
        return None, error_result(
            "LLAMA_SERVER_TIMEOUT", f"llama-server timed out after {_TIMEOUT}s"
        )
    except Exception as e:
        return None, error_result(
            "LLAMA_SERVER_ERROR", f"unexpected error talking to llama-server: {e}"
        )

    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        return None, error_result(
            "INVALID_VISION_RESPONSE",
            f"unexpected response shape: {json.dumps(data)[:300]}",
        )
    return data, None


async def _inspect(image_path, task) -> CallToolResult:
    image_path = Path(image_path).expanduser()
    if not image_path.is_file():
        return error_result("IMAGE_NOT_FOUND", f"image not found: {image_path}")
    if image_path.suffix.lower() not in SUPPORTED_EXT:
        return error_result(
            "IMAGE_NOT_SUPPORTED",
            f"unsupported image type '{image_path.suffix}'; supported: {', '.join(sorted(SUPPORTED_EXT))}",
        )

    image_data, err = _read_image(image_path)
    if err is not None or image_data is None:
        return (
            err
            if err is not None
            else error_result("IMAGE_READ_ERROR", "no image data")
        )

    if not any(image_data.startswith(m) for m in MAGIC):
        return error_result(
            "IMAGE_NOT_SUPPORTED", f"file is not a supported image: {image_path}"
        )

    mime, _ = mimetypes.guess_type(image_path.name)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"

    image_hash = _sha256(image_data)
    req_id = hashlib.sha256(os.urandom(16)).hexdigest()[:8]
    cache_file = _cache_path(image_hash, task, _MODEL_ID)
    log.info(
        "request=%s image=%s hash=%s task=%r", req_id, image_path, image_hash, task
    )

    cached = _read_cache(cache_file)
    if cached is not None and cached.get("success"):
        log.info("request=%s cache hit", req_id)
        cached["cache_hit"] = True
        return CallToolResult(
            content=[
                TextContent(type="text", text=json.dumps(cached, ensure_ascii=False))
            ]
        )

    async with _LOCK:
        cached = _read_cache(cache_file)
        if cached is not None and cached.get("success"):
            log.info("request=%s cache hit (post-lock)", req_id)
            cached["cache_hit"] = True
            return CallToolResult(
                content=[
                    TextContent(
                        type="text", text=json.dumps(cached, ensure_ascii=False)
                    )
                ]
            )

        start = time.time()
        resp, err = await asyncio.to_thread(_call_llama, image_data, mime, task)
        dur = round(time.time() - start, 2)
        if err or resp is None:
            if err is None:
                err = error_result(
                    "LLAMA_SERVER_ERROR", "llama-server returned no data"
                )
            log.info(
                "request=%s llama error after %ss: %s", req_id, dur, err.content[0].text
            )
            return err

        content = resp["choices"][0]["message"]["content"].strip()
        result = {
            "success": True,
            "summary": content,
            "details": "",
            "warnings": [],
            "cache_hit": False,
        }
        usage = resp.get("usage", {})
        log.info(
            "request=%s llama ok in %ss tokens=%s",
            req_id,
            dur,
            usage.get("total_tokens"),
        )
        if not _write_cache(cache_file, result):
            log.warning("request=%s cache write failed", req_id)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))]
    )


async def _on_list_tools(ctx, params):
    return ListToolsResult(
        tools=[
            Tool(
                name="vision.inspect",
                description="Analyze a local image file with the Qwen3-VL vision model. Returns structured JSON with the vision analysis.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "image_path": {
                            "type": "string",
                            "description": "Absolute path to the image file on this machine.",
                        },
                        "task": {
                            "type": "string",
                            "description": "What to look for / what the vision model should analyze.",
                        },
                    },
                    "required": ["image_path", "task"],
                },
            )
        ]
    )


async def _on_call_tool(ctx, params: CallToolRequestParams):
    if params.name != "vision.inspect":
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": False,
                            "error": {"code": "UNKNOWN_TOOL", "message": params.name},
                            "cache_hit": False,
                        }
                    ),
                )
            ],
            is_error=True,
        )
    args = params.arguments or {}
    image_path = args.get("image_path")
    task = args.get("task")
    if not image_path or not task:
        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": False,
                            "error": {
                                "code": "INVALID_ARGUMENTS",
                                "message": "image_path and task are required",
                            },
                            "cache_hit": False,
                        }
                    ),
                )
            ],
            is_error=True,
        )
    return await _inspect(image_path, task)


def _build_server():
    return Server(
        "mata-kadalz",
        version="1.0.0",
        on_list_tools=_on_list_tools,
        on_call_tool=_on_call_tool,
    )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="mata-kadalz",
        description="Local vision MCP server (Qwen3-VL via llama-server). stdio or streamable HTTP.",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=9932, help="HTTP bind port (default: 9932)"
    )
    parser.add_argument(
        "--path", default="/mcp", help="streamable HTTP path (default: /mcp)"
    )
    parser.add_argument(
        "--once", action="store_true", help="read one request from stdin and exit"
    )
    return parser.parse_args(argv)


def cli():
    asyncio.run(main())


async def main():
    args = _parse_args()

    _RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    setup_logging()

    if args.once:
        line = sys.stdin.buffer.readline()
        params = json.loads(line)
        res = await _inspect(params["image_path"], params["task"])
        print(json.dumps(json.loads(res.content[0].text)))
        return

    server = _build_server()

    if args.transport == "http":
        import uvicorn

        app = server.streamable_http_app(streamable_http_path=args.path)
        config = uvicorn.Config(app, host=args.host, port=args.port, log_level="info")
        uvicorn_server = uvicorn.Server(config)
        log.info("serving streamable HTTP on %s:%s%s", args.host, args.port, args.path)
        await uvicorn_server.serve()
        return

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    cli()
