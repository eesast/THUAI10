from __future__ import annotations

import argparse
import json
import threading
import urllib.request
import webbrowser

import uvicorn

from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="THUAI10 MuJoCo 局域网选手平台")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8767, type=int)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    local_url = f"http://127.0.0.1:{args.port}"
    try:
        with urllib.request.urlopen(local_url + "/api/status", timeout=0.8) as response:
            running = json.load(response).get("name") == "THUAI10 MuJoCo"
    except (OSError, ValueError):
        running = False
    if running:
        print(f"平台已经运行：{local_url}", flush=True)
        if args.open:
            webbrowser.open(local_url)
        return
    if args.open:
        threading.Timer(1.5, lambda: webbrowser.open(local_url)).start()
    print(f"选手平台：http://127.0.0.1:{args.port}；首次打开创建管理员，无默认密码。", flush=True)
    uvicorn.run(
        create_app(),
        host=args.host,
        port=args.port,
        proxy_headers=False,
        workers=1,
        limit_concurrency=64,
    )


if __name__ == "__main__":
    main()
