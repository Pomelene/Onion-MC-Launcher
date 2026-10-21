# -*- coding: utf-8 -*-
"""测试基建：临时工作区 + 本地 FakeServer（支持 Range、错误码、记录请求）。"""

import contextlib
import http.server
import tempfile
import threading
from pathlib import Path


class FakeServer:
    """按 routes（path -> bytes/str/callable）响应的本地 HTTP 服务器。"""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.httpd = None
        self.thread = None
        self.requests = []
        self.ranges = []

    def start(self):
        routes, requests, ranges = self.routes, self.requests, self.ranges

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                requests.append(self.path)
                if self.headers.get("Range"):
                    ranges.append(self.headers.get("Range"))
                handler = routes.get(self.path)
                if handler is None:
                    self.send_error(404)
                    return
                if callable(handler):
                    handler(self)
                    return
                data = handler.encode("utf-8") if isinstance(handler, str) else handler
                start = 0
                code = 200
                rng = self.headers.get("Range")
                if rng and rng.startswith("bytes="):
                    try:
                        start = int(rng[6:].split("-")[0])
                        code = 206
                    except ValueError:
                        start = 0
                if start >= len(data):
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{len(data)}")
                    self.end_headers()
                    return
                body = data[start:]
                self.send_response(code)
                self.send_header("Content-Length", str(len(body)))
                if code == 206:
                    self.send_header("Content-Range", f"bytes {start}-{len(data)-1}/{len(data)}")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def url(self, path=""):
        return f"http://127.0.0.1:{self.httpd.server_address[1]}{path}"

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()


@contextlib.contextmanager
def temp_workspace():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
