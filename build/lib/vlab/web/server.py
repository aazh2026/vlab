# -*- coding: utf-8 -*-
"""本地面板服务 / Local dashboard server.

只用 Python 标准库（``http.server``），零第三方依赖。

路由
----
``/``            面板页面（HTML）
``/api/report``  回测报告 JSON
``/api/rebuild`` 重新抓取数据并生成报告（POST/GET 均可）
``/healthz``     健康检查
"""
from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 8765
DEFAULT_HOST = "0.0.0.0"


class DashboardHandler(BaseHTTPRequestHandler):
    data_dir = DATA_DIR = ""
    web_dir = WEB_DIR = ""
    cache_path = ""
    server_version = "vlab/1.0"

    def log_message(self, fmt, *args):  # 静音默认日志
        pass

    # -- helpers ----------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, cache: bool = False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=300" if cache else "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, obj, code: int = 200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _file(self, path: str, ctype: str):
        if not os.path.exists(path):
            self._json({"error": "not found", "path": path}, 404)
            return
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    # -- routes -----------------------------------------------------------
    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._file(os.path.join(self.web_dir, "index.html"),
                       "text/html; charset=utf-8")
        elif path == "/api/report":
            if self.cache_path and os.path.exists(self.cache_path):
                with open(self.cache_path, "rb") as f:
                    self._send(200, f.read(), "application/json; charset=utf-8")
            else:
                self._json({"error": "report not built; run `python3 -m vlab report`"}, 503)
        elif path == "/api/rebuild":
            self._rebuild()
        elif path == "/healthz":
            self._json({"ok": True, "ts": time.time()})
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        self.do_GET()

    # -- rebuild ----------------------------------------------------------
    def _rebuild(self):
        """重新抓取数据并生成报告（耗时较长，异步执行）。"""
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        from vlab.datasource import fetch
        from vlab.engine import UNIVERSE, load_series
        from vlab.report import build_report, save

        def work():
            try:
                codes = [c for c, *_ in UNIVERSE] + [
                    "ixsh000300", "ixsh000922", "ixsh000015", "ixsh000905"]
                for c in dict.fromkeys(codes):
                    fetch(c, self.data_dir)
                series = load_series(data_dir=self.data_dir)
                rep = build_report(series)
                save(rep, self.cache_path)
            except Exception as e:  # pragma: no cover
                print("rebuild failed:", e)

        t = threading.Thread(target=work, daemon=True)
        t.start()
        self._json({"status": "rebuilding", "note": "数据抓取与回测在后台进行，稍后刷新页面"})


def serve(port: int = DEFAULT_PORT, data_dir: str = "", web_dir: str = "",
          host: str = DEFAULT_HOST, cache_path: str = "") -> None:
    """启动面板服务（阻塞）。"""
    DashboardHandler.data_dir = data_dir
    DashboardHandler.web_dir = web_dir
    DashboardHandler.cache_path = cache_path
    srv = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"vlab dashboard serving on http://{host}:{port}")
    print(f"  data : {data_dir}")
    print(f"  web  : {web_dir}")
    print("  Ctrl+C to stop")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        srv.server_close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--host", default=DEFAULT_HOST)
    a = ap.parse_args()
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    serve(port=a.port,
          data_dir=os.path.join(here, "data"),
          web_dir=os.path.join(here, "src", "vlab", "web"),
          cache_path=os.path.join(here, "results", "report.json"))
