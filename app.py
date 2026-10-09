#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
返投招商 Skill —— 本地前端服务

启动：
    python3 app.py            # 默认 http://127.0.0.1:8848
    python3 app.py 9000       # 指定端口

仅绑定 127.0.0.1（本机），不对外暴露。
"""
import json
import os
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import engine

BASE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(BASE, "web")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("  %s\n" % (fmt % args))

    # ---------------------------------------------------------- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False, default=str)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, code, msg):
        self._send(code, {"ok": False, "error": msg})

    # ------------------------------------------------------------- GET
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        try:
            if path in ("/", "/index.html"):
                self._serve_static("index.html")
                return

            if path == "/api/options":
                self._send(200, {"ok": True, "options": engine.list_options()})
                return

            if path == "/api/run":
                city = (qs.get("city") or [""])[0]
                industry = (qs.get("industry") or [""])[0]
                fund = (qs.get("fund") or [""])[0] or None
                depth = (qs.get("depth") or ["standard"])[0]
                live = (qs.get("live") or ["0"])[0] in ("1", "true", "yes")
                if not city or not industry:
                    self._err(400, "缺少参数：city / industry")
                    return
                result = engine.run(city, industry, fund, depth, live=live)
                self._send(200, {"ok": True, "result": result})
                return

            if path == "/api/datasources":
                import datasources
                self._send(200, {"ok": True, "sources": datasources.describe_all()})
                return

            # 其它静态资源（fallback.js 等）
            name = os.path.basename(path)
            fp = os.path.join(WEB_DIR, name)
            if name and os.path.isfile(fp):
                self._serve_static(name)
                return

            self._err(404, f"未找到路径 {path}")

        except ValueError as e:
            self._err(400, str(e))
        except Exception as e:  # noqa
            self._err(500, f"{type(e).__name__}: {e}")

    def _serve_static(self, name):
        fp = os.path.join(WEB_DIR, os.path.basename(name))
        ctype = "text/html; charset=utf-8" if name.endswith(".html") else \
                "application/javascript; charset=utf-8" if name.endswith(".js") else \
                "text/plain; charset=utf-8"
        with open(fp, encoding="utf-8") as f:
            self._send(200, f.read(), ctype)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8848
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("=" * 60)
    print("  返投招商 Skill 已启动")
    print(f"  请在浏览器打开：http://127.0.0.1:{port}")
    print("  按 Ctrl+C 停止")
    print("=" * 60)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
        srv.shutdown()


if __name__ == "__main__":
    main()
