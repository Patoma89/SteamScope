"""
Servidor HTTP local silencioso y seguro para SteamScope 3.0 NEXT (Edge WebView2).
Sirve los archivos estáticos de web_ui/, el ícono oficial y assets cacheados en AppData/cache
bloqueando cualquier intento de path traversal.
"""
import http.server
import mimetypes
import os
import socketserver
import threading
import urllib.parse
from typing import Optional

from core.config import obtener_ruta_appdata, obtener_ruta_recurso


def resolve_web_asset_path(rel_path: str, cache_dir: Optional[str] = None) -> Optional[str]:
    """Resuelve de forma segura una ruta relativa bajo /cache/ bloqueando path traversal."""
    cleaned = (rel_path or "").replace("\\", "/").lstrip("/")
    if not cleaned:
        return None
    parts = [p for p in cleaned.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None

    base_cache = cache_dir or os.path.join(obtener_ruta_appdata(), "cache")
    real_root = os.path.realpath(base_cache)
    candidate = os.path.realpath(os.path.join(real_root, *parts))

    try:
        if os.path.commonpath([candidate, real_root]) != real_root:
            return None
    except ValueError:
        return None

    if os.path.isfile(candidate):
        return candidate
    return None


class _QuietThreadedTCPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class _SteamScopeAssetHandler(http.server.BaseHTTPRequestHandler):
    web_ui_dir: str = ""
    cache_dir: Optional[str] = None

    def log_message(self, format: str, *args) -> None:
        return

    def _send_file(self, file_path: str, cache_max_age: int = 0) -> None:
        if not file_path or not os.path.isfile(file_path):
            self.send_error(404, "Not Found")
            return
        ctype, _ = mimetypes.guess_type(file_path)
        if file_path.lower().endswith(".ico"):
            ctype = "image/x-icon"
        ctype = ctype or "application/octet-stream"
        try:
            with open(file_path, "rb") as f:
                data = f.read()
        except OSError:
            self.send_error(500, "Read Error")
            return

        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cache_max_age > 0:
            self.send_header("Cache-Control", f"public, max-age={cache_max_age}")
        else:
            self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        rel = urllib.parse.unquote(parsed.path)

        if rel.startswith("/cache/"):
            raw_sub = rel[len("/cache/"):]
            if ".." in raw_sub.replace("\\", "/").split("/"):
                self.send_error(403, "Forbidden")
                return
            asset_path = resolve_web_asset_path(raw_sub, cache_dir=self.cache_dir)
            self._send_file(asset_path or "", cache_max_age=86400)
            return

        if rel == "/assets/icono.ico":
            ico_path = obtener_ruta_recurso("icono.ico")
            self._send_file(ico_path, cache_max_age=86400)
            return

        if rel in ("", "/"):
            rel = "/index.html"

        clean_rel = rel.lstrip("/").replace("/", os.sep)
        root = os.path.realpath(self.web_ui_dir)
        target = os.path.realpath(os.path.join(root, clean_rel))
        try:
            if os.path.commonpath([target, root]) != root:
                self.send_error(403, "Forbidden")
                return
        except ValueError:
            self.send_error(403, "Forbidden")
            return

        self._send_file(target, cache_max_age=0)


def start_local_server(web_ui_dir: str, cache_dir: Optional[str] = None) -> tuple[_QuietThreadedTCPServer, str]:
    """Inicia el servidor local HTTP en 127.0.0.1 con puerto efímero y retorna (httpd, url)."""
    handler_cls = type(
        "_BoundSteamScopeAssetHandler",
        (_SteamScopeAssetHandler,),
        {"web_ui_dir": web_ui_dir, "cache_dir": cache_dir},
    )
    httpd = _QuietThreadedTCPServer(("127.0.0.1", 0), handler_cls)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, f"http://127.0.0.1:{port}/index.html"
