"""极简生产服务器：静态站 + 广告位 302 + 订阅收集 + 付费链接鉴权。

不用 Flask/FastAPI，标准库 http.server 足够扛住几百 UV——50 块的机器
装 pip 包反而容易把内存吃满。前面套 Nginx 做 TLS 和缓存。

    python3 serve.py --port 8080 --root site
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import posixpath
import sys
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.config import db_path, load_config
from core.publish import paid_slug
from core.store import Store

CFG = load_config()
ROOT = Path("site")
ADMIN = os.environ.get("ADMIN_TOKEN", "")
STORE: Store | None = None


def store() -> Store:
    global STORE
    if STORE is None:
        STORE = Store(db_path())
    return STORE


class Handler(BaseHTTPRequestHandler):
    server_version = "MoneyBot/1.0"

    def log_message(self, fmt, *args):  # 精简日志，省磁盘
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    # ---------- helpers ----------
    def _send(self, code: int, body: bytes = b"", ctype: str = "text/html; charset=utf-8",
              extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def _redirect(self, url: str, code: int = 302):
        self._send(code, b"", "text/plain", {"Location": url})

    def _client_ip(self) -> str:
        fwd = self.headers.get("X-Forwarded-For", "")
        ip = fwd.split(",")[0].strip() if fwd else self.client_address[0]
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

    def _static(self, path: str):
        path = urllib.parse.unquote(path)
        rel = posixpath.normpath("/" + path).lstrip("/")
        if rel.startswith("..") or ".." in rel.split("/"):
            return self._send(403, b"forbidden")
        target = ROOT / rel
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            return self._send(404, b"404 not found")
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/xml", "application/json"):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    # ---------- routes ----------
    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        path = u.path

        if path.startswith("/go/"):
            name = path[4:]
            affs = CFG["monetize"].get("affiliates", [])
            if name.endswith(".html"):
                name = name[:-5]
            try:
                idx = int(name.lstrip("a"))
                target = affs[idx]["url"]
            except (ValueError, IndexError):
                return self._send(404, b"bad slot")
            store().log_click(None, f"a{idx}", target, self._client_ip())
            return self._redirect(target)

        if path.startswith("/p/"):
            tok = path[3:].strip("/")
            row = store().subscriber_by_token(tok)
            if not row:
                return self._send(403, "链接无效，请联系作者重新获取。".encode())
            if row["tier"] != "paid":
                return self._redirect(CFG["monetize"].get("buy_url", "/"))
            issues = store().list_issues(1)
            if not issues:
                return self._send(404, b"no issue yet")
            return self._redirect("/paid/" + paid_slug(CFG, issues[0]["issue_no"]))

        if path == "/api/stats":
            if not ADMIN or self.headers.get("X-Admin-Token") != ADMIN:
                return self._send(401, b"unauthorized")
            return self._json(200, store().stats())

        if path in ("/", ""):
            return self._static("/index.html")
        return self._static(path)

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""

        if u.path == "/api/click":
            q = urllib.parse.parse_qs(u.query)
            slot = q.get("slot", [""])[0]
            store().log_click(None, slot, "", self._client_ip())
            return self._send(204)

        if u.path == "/api/subscribe":
            try:
                data = json.loads(raw or b"{}")
                contact = str(data.get("contact", "")).strip()
            except json.JSONDecodeError:
                contact = ""
            if not contact or len(contact) > 120 or ("@" not in contact and len(contact) < 5):
                return self._json(400, {"ok": False, "error": "留下邮箱或微信号"})
            token = store().add_subscriber(contact)
            base = CFG["site"]["base_url"].rstrip("/")
            return self._json(200, {"ok": True, "token": token,
                                    "free_link": f"{base}/p/{token}",
                                    "hint": "付费后凭邮箱可解锁完整版"})

        return self._send(404, b"not found")


def main() -> int:
    global ROOT
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    ap.add_argument("--root", default=os.environ.get("SITE_ROOT", "site"))
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()
    ROOT = Path(args.root)
    if not (ROOT / "index.html").exists():
        print(f"!! {ROOT}/index.html 不存在，先跑 python3 main.py run")
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"serving {ROOT.resolve()} on http://{args.host}:{args.port}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
