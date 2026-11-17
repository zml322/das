"""本机静态服务：加载生产构建，并为 Vue 路由回退到首页。"""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread


class FrontendHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if not Path(self.translate_path(path)).is_file() and "." not in path.rsplit("/", 1)[-1]:
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, *_args):
        pass


class FrontendServer:
    def __init__(self, directory):
        handler = partial(FrontendHandler, directory=str(directory))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
