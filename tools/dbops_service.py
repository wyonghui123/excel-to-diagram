"""dbops_service.py - 数据库运维 HTTP 服务 [V007.63 2026-07-14]
[L13.3 集成 audit_recovery]

端口: 9204
端点:
  GET /api?token=XXX
  GET /api/audit/recover/find?object_type=X&object_id=N&token=XXX
  GET /api/audit/recover/preview?object_type=X&object_id=N&token=XXX
  GET /api/audit/recover/restore?object_type=X&object_id=N&token=XXX&confirm=yes-i-know&dry_run=true

[L11.3] DELETE 二次确认: confirm=yes-i-know
"""
import os
import sys
import json
import time
import hashlib
import http.server
import socketserver
from urllib.parse import urlparse, parse_qs

VERSION = "v0.1"
PORT = int(os.environ.get("DBOPS_SERVICE_PORT", 9204))
SECRET = os.environ.get("DBOPS_SERVICE_SECRET", "v007.63-dbops")
DB_PATH = os.environ.get(
    "DBOPS_SERVICE_DB_PATH",
    "/opt/app/deployments/meta/architecture.db"
)

# 延迟导入 audit_recovery (避免在没有 audit_recovery.py 的环境 crash)
sys.path.insert(0, "/opt/app/shared")
try:
    from audit_recovery import AuditRecovery
except ImportError:
    AuditRecovery = None  # type: ignore


def check_token(token: str) -> bool:
    """时变 token: sha256(secret:hour)[:16]"""
    if not token:
        return False
    expected = hashlib.sha256(
        f"{SECRET}:{int(time.time()) // 3600}".encode()
    ).hexdigest()[:16]
    return token == expected


class Handler(http.server.BaseHTTPRequestHandler):
    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        qs = parse_qs(url.query)
        token = qs.get("token", [""])[0]
        if not check_token(token):
            return self._json(403, {"error": "token required"})

        if url.path == "/api":
            return self._json(200, {
                "service": "dbops_service",
                "version": VERSION,
                "port": PORT,
                "audit_recovery_available": AuditRecovery is not None,
                "endpoints": [
                    "/api/audit/recover/find",
                    "/api/audit/recover/preview",
                    "/api/audit/recover/restore",
                ],
            })

        if url.path == "/api/audit/recover/find":
            return self._handle_find(qs)
        if url.path == "/api/audit/recover/preview":
            return self._handle_preview(qs)
        if url.path == "/api/audit/recover/restore":
            return self._handle_restore(qs)

        return self._json(404, {"error": "not found"})

    def _require_audit_recovery(self):
        if not AuditRecovery:
            return self._json(500, {"error": "audit_recovery module not available"})
        return None

    def _parse_obj(self, qs):
        obj_type = qs.get("object_type", [""])[0]
        obj_id_raw = qs.get("object_id", ["0"])[0]
        try:
            obj_id = int(obj_id_raw)
        except ValueError:
            obj_id = 0
        if not obj_type or not obj_id:
            return None, None, self._json(400, {"error": "object_type and object_id required"})
        return obj_type, obj_id, None

    def _handle_find(self, qs):
        obj_type, obj_id, err = self._parse_obj(qs)
        if err:
            return err
        na = self._require_audit_recovery()
        if na:
            return na
        with AuditRecovery(DB_PATH) as ar:
            return self._json(200, ar.find_recoverable(obj_type, obj_id))

    def _handle_preview(self, qs):
        obj_type, obj_id, err = self._parse_obj(qs)
        if err:
            return err
        na = self._require_audit_recovery()
        if na:
            return na
        with AuditRecovery(DB_PATH) as ar:
            find_result = ar.find_recoverable(obj_type, obj_id)
            preview_lines = ar.preview(obj_type, obj_id)
        return self._json(200, {
            "find_result": find_result,
            "preview": preview_lines,
        })

    def _handle_restore(self, qs):
        obj_type, obj_id, err = self._parse_obj(qs)
        if err:
            return err
        dry_run = qs.get("dry_run", ["true"])[0] == "true"
        skip_warnings = qs.get("skip_warnings", ["false"])[0] == "true"
        # [L11.3] DELETE 二次确认
        confirm = qs.get("confirm", [""])[0]
        if not dry_run and confirm != "yes-i-know":
            return self._json(400, {
                "error": "non-dry-run requires confirm=yes-i-know",
                "warning": "This will modify production database. Read HANDOFF_object_recovery.md first.",
            })
        na = self._require_audit_recovery()
        if na:
            return na
        with AuditRecovery(DB_PATH) as ar:
            result = ar.restore(
                obj_type, obj_id,
                dry_run=dry_run,
                skip_warnings=skip_warnings,
            )
        return self._json(200, result)

    def log_message(self, fmt, *args):
        sys.stderr.write("[dbops_service] %s - - %s\n" % (self.address_string(), fmt % args))


def main():
    print(f"[dbops_service] v{VERSION} on port {PORT}", flush=True)
    print(f"[dbops_service] DB_PATH={DB_PATH}", flush=True)
    print(f"[dbops_service] AuditRecovery={AuditRecovery is not None}", flush=True)
    with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()