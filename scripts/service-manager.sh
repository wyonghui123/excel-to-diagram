#!/usr/bin/env bash
# ============================================================
# 服务管理脚本
# 统一管理所有服务的启停和状态
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/environment/server-prod.toml"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 从配置读取值
get_config() {
    local section="$1"
    local key="$2"
    
    awk -F'=' -v section="[$section]" '
        BEGIN { in_section=0 }
        /^\[/ { in_section = ($0 == section) }
        in_section && $1 ~ /^'"$key"'$/ {
            gsub(/[ \t]+/, "", $0)
            sub(/^'"$key"'[ \t]*=[ \t]*/, "")
            gsub(/[ \t"]/, "", $0)
            print $0
            exit
        }
    ' "$CONFIG_FILE" 2>/dev/null || echo ""
}

log() { echo "[$(date '+%H:%M:%S')] $*"; }

# 服务配置
FRONTEND_PORT=$(get_config "services.frontend" "port" || echo "8081")
BACKEND_PORT=$(get_config "services.backend" "port" || echo "5001")
FRONTEND_WORKDIR=$(get_config "services.frontend" "work_dir" || echo "/opt/app")
BACKEND_WORKDIR=$(get_config "services.frontend" "work_dir" || echo "/opt/app/meta")
PYTHON=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")

# 状态文件
PID_DIR="/opt/app/state"
mkdir -p "$PID_DIR"

# ============================================================
# 获取进程 PID
# ============================================================
get_pid() {
    local port="$1"
    netstat -tlnp 2>/dev/null | grep ":${port} " | awk '{print $7}' | cut -d'/' -f1 | head -1
}

# ============================================================
# 检查服务状态
# ============================================================
check_status() {
    local port="$1"
    local name="$2"
    
    local pid=$(get_pid "$port")
    
    if [[ -n "$pid" ]]; then
        local status=$(ps -p "$pid" -o state= 2>/dev/null | tr -d ' ')
        local uptime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
        echo -e "${GREEN}●${NC} $name (端口 $port) - PID: $pid, 运行时间: $uptime"
        return 0
    else
        echo -e "${RED}○${NC} $name (端口 $port) - 未运行"
        return 1
    fi
}

# ============================================================
# 启动服务
# ============================================================
start_service() {
    local name="$1"
    local port="$2"
    local workdir="$3"
    
    log "启动 $name (端口: $port)..."
    
    # 检查是否已运行
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo -e "${YELLOW}服务 $name 已在运行${NC}"
        return 0
    fi
    
    # 切换到工作目录
    cd "$workdir" 2>/dev/null || {
        echo -e "${RED}工作目录不存在: $workdir${NC}"
        return 1
    }
    
    # 查找 server.py
    local server_script="$workdir/server.py"
    if [[ ! -f "$server_script" ]]; then
        server_script="$workdir/meta/server.py"
    fi
    
    if [[ ! -f "$server_script" ]]; then
        echo -e "${RED}未找到启动脚本: $server_script${NC}"
        return 1
    fi
    
    # 启动服务
    export PORT="$port"
    nohup $PYTHON "$server_script" > "/opt/app/shared/logs/${name}.log" 2>&1 &
    
    local pid=$!
    echo "$pid" > "$PID_DIR/${name}.pid"
    
    # 等待服务启动
    sleep 3
    
    # 验证
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo -e "${GREEN}✓ $name 启动成功 (PID: $pid)${NC}"
        return 0
    else
        echo -e "${RED}✗ $name 启动失败${NC}"
        rm -f "$PID_DIR/${name}.pid"
        return 1
    fi
}

# ============================================================
# 停止服务
# ============================================================
stop_service() {
    local name="$1"
    local port="$2"
    
    log "停止 $name (端口: $port)..."
    
    local pid=$(get_pid "$port")
    
    if [[ -z "$pid" ]]; then
        echo -e "${YELLOW}服务 $name 未运行${NC}"
        return 0
    fi
    
    # 优雅停止
    kill "$pid" 2>/dev/null || true
    
    # 等待进程退出
    local count=0
    while kill -0 "$pid" 2>/dev/null && [[ $count -lt 10 ]]; do
        sleep 1
        ((count++))
    done
    
    # 强制杀死
    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
    fi
    
    # 清理 PID 文件
    rm -f "$PID_DIR/${name}.pid"
    
    # 确认停止
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        echo -e "${RED}✗ $name 停止失败${NC}"
        return 1
    else
        echo -e "${GREEN}✓ $name 已停止${NC}"
        return 0
    fi
}

# ============================================================
# 重启服务
# ============================================================
restart_service() {
    local name="$1"
    local port="$2"
    local workdir="$3"
    
    stop_service "$name" "$port"
    sleep 2
    start_service "$name" "$port" "$workdir"
}

# ============================================================
# 健康检查
# ============================================================
health_check() {
    local name="$1"
    local port="$2"
    
    local endpoint=$(get_config "services.${name}" "health_endpoint" || echo "/health")
    local timeout=$(get_config "services.${name}" "check_timeout" || echo "5")
    
    if curl -sf --max-time "$timeout" "http://localhost:${port}${endpoint}" > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name 健康检查通过"
        return 0
    else
        echo -e "${RED}✗${NC} $name 健康检查失败"
        return 1
    fi
}

# ============================================================
# 状态显示
# ============================================================
show_status() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}         服务状态${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    
    check_status "frontend" "$FRONTEND_PORT"
    check_status "backend" "$BACKEND_PORT"
    
    echo ""
    
    # 健康检查
    echo -e "${BLUE}健康检查:${NC}"
    health_check "frontend" "$FRONTEND_PORT" || true
    health_check "backend" "$BACKEND_PORT" || true
    
    echo ""
    echo "日志:"
    echo "  前端: /opt/app/shared/logs/frontend.log"
    echo "  后端: /opt/app/shared/logs/backend.log"
    echo ""
}

# ============================================================
# 主流程
# ============================================================
case "${1:-status}" in
    start)
        case "${2:-all}" in
            frontend) start_service "frontend" "$FRONTEND_PORT" "$FRONTEND_WORKDIR" ;;
            backend) start_service "backend" "$BACKEND_PORT" "$BACKEND_WORKDIR" ;;
            all)
                start_service "backend" "$BACKEND_PORT" "$BACKEND_WORKDIR"
                sleep 2
                start_service "frontend" "$FRONTEND_PORT" "$FRONTEND_WORKDIR"
                ;;
        esac
        ;;
    
    stop)
        case "${2:-all}" in
            frontend) stop_service "frontend" "$FRONTEND_PORT" ;;
            backend) stop_service "backend" "$BACKEND_PORT" ;;
            all)
                stop_service "frontend" "$FRONTEND_PORT"
                stop_service "backend" "$BACKEND_PORT"
                ;;
        esac
        ;;
    
    restart)
        case "${2:-all}" in
            frontend) restart_service "frontend" "$FRONTEND_PORT" "$FRONTEND_WORKDIR" ;;
            backend) restart_service "backend" "$BACKEND_PORT" "$BACKEND_WORKDIR" ;;
            all)
                restart_service "backend" "$BACKEND_PORT" "$BACKEND_WORKDIR"
                sleep 2
                restart_service "frontend" "$FRONTEND_PORT" "$FRONTEND_WORKDIR"
                ;;
        esac
        ;;
    
    status)
        show_status
        ;;
    
    health)
        echo -e "${BLUE}健康检查:${NC}"
        health_check "frontend" "$FRONTEND_PORT"
        health_check "backend" "$BACKEND_PORT"
        ;;
    
    *)
        echo "用法: $0 {start|stop|restart|status|health} [frontend|backend|all]"
        echo ""
        echo "  start   [service]  - 启动服务"
        echo "  stop    [service]  - 停止服务"
        echo "  restart [service]  - 重启服务"
        echo "  status             - 显示所有服务状态"
        echo "  health             - 健康检查"
        echo ""
        echo "示例:"
        echo "  $0 start all      - 启动所有服务"
        echo "  $0 stop backend   - 停止后端服务"
        echo "  $0 restart frontend - 重启前端服务"
        ;;
esac
