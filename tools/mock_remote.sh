#!/usr/bin/env bash
# ============================================================
# mock_remote.sh - 本地创建 mock 远端环境
# ============================================================
# 用途: 在本地 (Windows/Linux) 创建 /opt/app 的 mock 镜像,
#       演练 deploy_step.sh / precheck_remote.sh 等
# 用法:
#   bash tools/mock_remote.sh setup     # 创建 mock 环境
#   bash tools/mock_remote.sh teardown  # 删除
#   bash tools/mock_remote.sh status    # 看状态
# ============================================================

set -e

# 配置
MOCK_ROOT="${MOCK_ROOT:-/tmp/mock_remote}"
# Windows 兼容
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
    MOCK_ROOT="${MOCK_ROOT:-$(cygpath -u "$TEMP")/mock_remote}"
fi

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

hr() { echo -e "${CYAN}============================================================${NC}"; }
ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERR]${NC} $1"; exit 1; }

# ============================================================
# setup
# ============================================================
setup() {
    hr
    echo "  MOCK SETUP: $MOCK_ROOT"
    hr

    # 1. 创建目录结构 (模仿 /opt/app)
    mkdir -p "$MOCK_ROOT/opt/app/deployments/v20260630_003/backend"
    mkdir -p "$MOCK_ROOT/opt/app/deployments/v20260702_001/backend"
    mkdir -p "$MOCK_ROOT/opt/app/shared/logs"
    mkdir -p "$MOCK_ROOT/opt/app/shared/data"
    mkdir -p "$MOCK_ROOT/opt/app/meta"
    mkdir -p "$MOCK_ROOT/etc/systemd/system"
    mkdir -p "$MOCK_ROOT/opt/miniconda3-py39/bin"

    ok "创建目录: $MOCK_ROOT"

    # 2. 创建 mock v003 server.py (最小可运行)
    cat > "$MOCK_ROOT/opt/app/deployments/v20260630_003/backend/server.py" <<'PYEOF'
"""Mock v003 server.py - minimal Flask app"""
import os
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 5000))

# Mock enum types data
MOCK_ENUMS = [
    {"id": 1, "code": "annotation_category", "name": "Annotation Category", "mutability": "fullEditable"},
    {"id": 2, "code": "relation_type", "name": "Relation Type", "mutability": "extensible"},
    {"id": 3, "code": "action_type", "name": "Action Type", "mutability": "locked"},
] * 7  # 21 total

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/api/v1/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "data": [],
                "page": 1,
                "page_size": 20,
                "total": 0
            }).encode())
        elif self.path == "/api/v1/enum-types":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "data": MOCK_ENUMS,
                "page": 1,
                "page_size": 20,
                "total": len(MOCK_ENUMS)
            }).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Mock v003 Frontend</body></html>")

    def log_message(self, format, *args):
        pass  # quiet

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Mock v003 server on port {PORT}", flush=True)
    server.serve_forever()
PYEOF
    ok "Mock v003 server.py"

    # 3. Mock v004 server.py (with telemetry try/except)
    cat > "$MOCK_ROOT/opt/app/deployments/v20260702_001/backend/server.py" <<'PYEOF'
"""Mock v004 server.py - minimal Flask app with telemetry try/except"""
import os
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.environ.get("PORT", 5001))

# Try to import telemetry (will fail in mock - 测试 try/except)
try:
    from telemetry import install_global_tracer
    install_global_tracer([])
except ImportError:
    print("[v004 PATCH] telemetry 模块未部署, 跳过", flush=True)

# Mock enum types data (same as v003)
MOCK_ENUMS = [
    {"id": 1, "code": "annotation_category", "name": "Annotation Category", "mutability": "fullEditable"},
    {"id": 2, "code": "relation_type", "name": "Relation Type", "mutability": "extensible"},
    {"id": 3, "code": "action_type", "name": "Action Type", "mutability": "locked"},
] * 7

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health" or self.path == "/api/v1/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "data": MOCK_ENUMS,
                "total": len(MOCK_ENUMS)
            }).encode())
        elif self.path == "/api/v1/enum-types":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "success": True,
                "data": MOCK_ENUMS,
                "total": len(MOCK_ENUMS)
            }).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body>Mock v004 Frontend</body></html>")

    def log_message(self, format, *args):
        pass  # quiet

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Mock v004 server on port {PORT}", flush=True)
    server.serve_forever()
PYEOF
    ok "Mock v004 server.py"

    # 4. Mock v003 db (空 db 但有 schema)
    if command -v sqlite3 >/dev/null 2>&1; then
        DB="$MOCK_ROOT/opt/app/deployments/v20260630_003/backend/architecture.db"
        sqlite3 "$DB" "CREATE TABLE IF NOT EXISTS enum_types (id INTEGER PRIMARY KEY, code TEXT, name TEXT, mutability TEXT);"
        sqlite3 "$DB" "INSERT OR IGNORE INTO enum_types VALUES (1, 'annotation_category', 'Annotation Category', 'fullEditable');"
        sqlite3 "$DB" "INSERT OR IGNORE INTO enum_types VALUES (2, 'relation_type', 'Relation Type', 'extensible');"
        sqlite3 "$DB" "INSERT OR IGNORE INTO enum_types VALUES (3, 'action_type', 'Action Type', 'locked');"
        ok "Mock v003 db: $DB"
    else
        warn "sqlite3 未找到, 跳过 db 创建 (deploy_step.sh 会用 fallback)"
    fi

    # 5. Mock service 文件
    cat > "$MOCK_ROOT/etc/systemd/system/excel-backend.service" <<'EOF'
[Unit]
Description=Excel to Diagram Backend (mock)
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/tmp/mock_remote/opt/app/current
ExecStart=/usr/bin/python3 server.py
Environment="PORT=5000"
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
    ok "Mock service file"

    # 6. Mock Python bin
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" || "$OSTYPE" == "cygwin" ]]; then
        # Windows: 直接用 python
        echo "Mock python (Windows)" > "$MOCK_ROOT/opt/miniconda3-py39/bin/python"
    else
        ln -sf "$(which python3)" "$MOCK_ROOT/opt/miniconda3-py39/bin/python" 2>/dev/null || \
            echo "Mock python" > "$MOCK_ROOT/opt/miniconda3-py39/bin/python"
    fi
    ok "Mock Python bin"

    # 7. Mock /opt/app/current 链接
    ln -sfn "$MOCK_ROOT/opt/app/deployments/v20260630_003/backend" "$MOCK_ROOT/opt/app/current"
    ok "Mock /opt/app/current -> v003"

    # 8. 保存环境配置
    cat > "$MOCK_ROOT/.env" <<EOF
# Mock remote environment
MOCK_ROOT=$MOCK_ROOT
EOF
    cat > "$MOCK_ROOT/setup_env.sh" <<'SETUP_EOF'
#!/usr/bin/env bash
# Source this to "enter" the mock environment
export MOCK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export DEPLOY_PATH="$MOCK_ROOT/opt/app/deployments/v20260702_001"
export BACKEND_PATH="$DEPLOY_PATH/backend"
export V003_PATH="$MOCK_ROOT/opt/app/deployments/v20260630_003"
export DB_SOURCE="$V003_PATH/backend/architecture.db"
export DB_TARGET="$BACKEND_PATH/architecture.db"
export LOG_DIR="$MOCK_ROOT/opt/app/shared/logs"
export PYTHON_BIN="$(which python3)"
export BACKEND_PORT=5001
export FRONTEND_PORT=8081
echo "Mock env loaded: MOCK_ROOT=$MOCK_ROOT"
SETUP_EOF
    chmod +x "$MOCK_ROOT/setup_env.sh"
    ok "Mock env config: source $MOCK_ROOT/setup_env.sh"

    hr
    echo -e "${GREEN}  MOCK SETUP COMPLETE${NC}"
    echo ""
    echo "Mock root: $MOCK_ROOT"
    echo ""
    echo "Usage:"
    echo "  source $MOCK_ROOT/setup_env.sh"
    echo "  bash tools/precheck_remote.sh  # 需在 mock root 内执行"
    echo "  bash tools/deploy_step.sh precheck"
    hr
}

# ============================================================
# teardown
# ============================================================
teardown() {
    hr
    echo "  MOCK TEARDOWN: $MOCK_ROOT"
    hr
    if [ -d "$MOCK_ROOT" ]; then
        # 先杀掉 mock 进程
        pkill -f "$MOCK_ROOT" 2>/dev/null || true
        sleep 1
        rm -rf "$MOCK_ROOT"
        ok "已删除 $MOCK_ROOT"
    else
        warn "$MOCK_ROOT 不存在"
    fi
}

# ============================================================
# status
# ============================================================
status() {
    hr
    echo "  MOCK STATUS"
    hr
    if [ ! -d "$MOCK_ROOT" ]; then
        warn "Mock root 不存在: $MOCK_ROOT"
        return 1
    fi
    echo "Mock root: $MOCK_ROOT"
    echo ""
    echo "目录结构:"
    find "$MOCK_ROOT" -type d 2>/dev/null | head -20
    echo ""
    echo "关键文件:"
    for f in "$MOCK_ROOT/opt/app/deployments/v20260630_003/backend/server.py" \
             "$MOCK_ROOT/opt/app/deployments/v20260702_001/backend/server.py" \
             "$MOCK_ROOT/etc/systemd/system/excel-backend.service" \
             "$MOCK_ROOT/opt/app/current"; do
        if [ -e "$f" ]; then
            ok "存在: $f"
        else
            warn "缺失: $f"
        fi
    done
    echo ""
    echo "监听端口 (5000/5001/8081):"
    ss -tln 2>/dev/null | grep -E ":(5000|5001|8081)" || echo "  (无)"
}

# ============================================================
# MAIN
# ============================================================
case "${1:-}" in
    setup)     setup ;;
    teardown)  teardown ;;
    status)    status ;;
    *)
        echo "Usage: $0 {setup|teardown|status}"
        echo ""
        echo "Environment:"
        echo "  MOCK_ROOT=$MOCK_ROOT (default: /tmp/mock_remote or %TEMP%/mock_remote on Windows)"
        exit 1
        ;;
esac
