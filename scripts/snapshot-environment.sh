#!/usr/bin/env bash
# ============================================================
# 环境快照脚本
# 记录当前环境状态，用于变更检测和问题追溯
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/environment/server-prod.toml"
SNAPSHOT_DIR="/opt/app/state"
SNAPSHOT_FILE="${SNAPSHOT_DIR}/environment-snapshot.json"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# 获取 Python 版本
get_python_info() {
    local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
    
    if [[ ! -x "$py_path" ]]; then
        echo '{"version": "not_found", "path": "'"$py_path"'"}'
        return
    fi
    
    local version=$($py_path --version 2>&1 | cut -d' ' -f2)
    local prefix=$($py_path -c "import sys; print(sys.prefix)" 2>/dev/null || echo "unknown")
    
    # 获取已安装的包
    local packages=$($py_path -c "
import pkg_resources
pkgs = sorted([p.project_name + '==' + p.version for p in pkg_resources.working_set])
print(','.join(pkgs))
" 2>/dev/null || echo "")
    
    cat << EOF
{
    "version": "$version",
    "path": "$py_path",
    "prefix": "$prefix",
    "packages": "$(echo "$packages" | tr ',' '\n' | head -20)"
}
EOF
}

# 获取服务状态
get_service_status() {
    local port="$1"
    local service_name="$2"
    
    local running=false
    local pid="null"
    local proc_name="null"
    
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        running=true
        pid=$(netstat -tlnp 2>/dev/null | grep ":${port} " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        proc_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
    fi
    
    cat << EOF
{
    "name": "$service_name",
    "port": $port,
    "running": $running,
    "pid": ${pid:-null},
    "process": "$proc_name"
}
EOF
}

# 获取目录信息
get_directory_info() {
    local base_dir=$(get_config "paths" "app_root" || echo "/opt/app")
    
    cat << EOF
{
    "app_root": "$base_dir",
    "directories": [
        {"path": "${base_dir}", "exists": $([ -d "$base_dir" ] && echo "true" || echo "false")},
        {"path": "${base_dir}/shared", "exists": $([ -d "${base_dir}/shared" ] && echo "true" || echo "false")},
        {"path": "${base_dir}/shared/data", "exists": $([ -d "${base_dir}/shared/data" ] && echo "true" || echo "false")},
        {"path": "${base_dir}/shared/logs", "exists": $([ -d "${base_dir}/shared/logs" ] && echo "true" || echo "false")},
        {"path": "${base_dir}/deployments", "exists": $([ -d "${base_dir}/deployments" ] && echo "true" || echo "false")},
        {"path": "${base_dir}/backups", "exists": $([ -d "${base_dir}/backups" ] && echo "true" || echo "false")}
    ]
}
EOF
}

# 获取数据库信息
get_database_info() {
    local db_dir=$(get_config "paths" "shared_data" || echo "/opt/app/shared/data")
    local db_file=$(get_config "database" "file" || echo "architecture.db")
    local db_path="$db_dir/$db_file"
    
    local exists=false
    local size="0"
    local tables="[]"
    local version="none"
    
    if [[ -f "$db_path" ]]; then
        exists=true
        size=$(stat -c%s "$db_path" 2>/dev/null || stat -f%z "$db_path" 2>/dev/null || echo "0")
        
        local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
        
        tables=$($py_path -c "
import sqlite3
try:
    conn = sqlite3.connect('$db_path')
    cursor = conn.cursor()
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")
    tables = [t[0] for t in cursor.fetchall()]
    conn.close()
    print(str(tables))
except:
    print('[]')
" 2>/dev/null || echo "[]")
        
        # 获取数据库版本
        version=$($py_path -c "
import sqlite3
try:
    conn = sqlite3.connect('$db_path')
    cursor = conn.cursor()
    cursor.execute(\"SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1\")
    result = cursor.fetchone()
    conn.close()
    print(result[0] if result else 'init')
except:
    print('unknown')
" 2>/dev/null || echo "unknown")
    fi
    
    cat << EOF
{
    "path": "$db_path",
    "exists": $exists,
    "size_bytes": $size,
    "tables": $tables,
    "schema_version": "$version"
}
EOF
}

# 生成快照
generate_snapshot() {
    log "生成环境快照..."
    
    # 确保目录存在
    mkdir -p "$SNAPSHOT_DIR"
    
    # 获取各项信息
    local python_info=$(get_python_info)
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local frontend_status=$(get_service_status "$frontend_port" "frontend")
    local backend_status=$(get_service_status "$backend_port" "backend")
    local dir_info=$(get_directory_info)
    local db_info=$(get_database_info)
    
    # 磁盘信息
    local disk_info=$(
        cat << EOF
{
    "total_gb": $(df -BG / 2>/dev/null | awk 'NR==2 {print $2}' | tr -d 'G'),
    "used_gb": $(df -BG / 2>/dev/null | awk 'NR==2 {print $3}' | tr -d 'G'),
    "available_gb": $(df -BG / 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')
}
EOF
    )
    
    # 内存信息
    local mem_info=$(
        cat << EOF
{
    "total_gb": $(free -g 2>/dev/null | awk 'NR==2 {print $2}'),
    "used_gb": $(free -g 2>/dev/null | awk 'NR==2 {print $3}'),
    "available_gb": $(free -g 2>/dev/null | awk 'NR==2 {print $4}')
}
EOF
    )
    
    # 组装完整快照
    cat > "$SNAPSHOT_FILE" << EOF
{
    "snapshot_time": "$(date -Iseconds)",
    "hostname": "$(hostname)",
    "os": "$(cat /etc/centos-release 2>/dev/null || cat /etc/redhat-release 2>/dev/null || echo 'unknown')",
    "kernel": "$(uname -r)",
    "uptime_seconds": $(cut -d. -f1 /proc/uptime 2>/dev/null || echo 0),
    
    "python": $python_info,
    
    "services": {
        "frontend": $frontend_status,
        "backend": $backend_status
    },
    
    "directories": $dir_info,
    
    "database": $db_info,
    
    "resources": {
        "disk": $disk_info,
        "memory": $mem_info,
        "cpu_cores": $(nproc 2>/dev/null || echo 1)
    },
    
    "network": {
        "hostname": "$(hostname -f 2>/dev/null || hostname)",
        "ip_addresses": [
            $(ip addr show 2>/dev/null | grep "inet " | awk '{print "\""$2"\"}' | tr '\n' ',' | sed 's/,$//')
        ]
    },
    
    "config_version": "$(get_config "metadata" "config_version" || echo 'unknown')"
}
EOF
    
    log "快照已保存: $SNAPSHOT_FILE"
    
    # 输出摘要
    echo ""
    echo -e "${GREEN}========== 环境快照摘要 ==========${NC}"
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "服务器: $(hostname)"
    echo ""
    echo "Python: $($py_path --version 2>&1 | cut -d' ' -f2)"
    echo "CPU: $(nproc 2>/dev/null || echo 1) 核"
    echo "内存: $(free -g 2>/dev/null | awk 'NR==2 {print $2}')GB"
    echo ""
    echo "服务状态:"
    echo "  前端 (${frontend_port}): $(netstat -tlnp 2>/dev/null | grep -q ":${frontend_port} " && echo -e "${GREEN}运行中${NC}" || echo -e "${YELLOW}未运行${NC}")"
    echo "  后端 (${backend_port}): $(netstat -tlnp 2>/dev/null | grep -q ":${backend_port} " && echo -e "${GREEN}运行中${NC}" || echo -e "${YELLOW}未运行${NC}")"
    echo ""
    echo "数据库: $db_info"
    echo -e "${GREEN}=================================${NC}"
}

# 恢复快照
restore_snapshot() {
    local snapshot_path="${1:-$SNAPSHOT_FILE}"
    
    if [[ ! -f "$snapshot_path" ]]; then
        echo "快照文件不存在: $snapshot_path"
        exit 1
    fi
    
    echo "快照文件:"
    cat "$snapshot_path" | python3 -m json.tool 2>/dev/null || cat "$snapshot_path"
}

# 比对快照
diff_snapshot() {
    local snapshot1="${1:-$SNAPSHOT_FILE}"
    local snapshot2="${2:-}"
    
    if [[ ! -f "$snapshot1" ]]; then
        echo "快照文件不存在: $snapshot1"
        exit 1
    fi
    
    echo "========== 当前快照 vs 历史快照 =========="
    echo ""
    
    # 简单比对 - 检查关键变化
    local current_py=$($(get_config "dependencies.python" "binary" || echo "python") --version 2>&1 | cut -d' ' -f2)
    local snapshot_py=$(grep '"version"' "$snapshot1" | head -1 | grep -oP '"\K[^"]+' || echo "unknown")
    
    if [[ "$current_py" != "$snapshot_py" ]]; then
        echo -e "${YELLOW}⚠ Python 版本变化: $snapshot_py -> $current_py${NC}"
    fi
    
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    if netstat -tlnp 2>/dev/null | grep -q ":${frontend_port} "; then
        echo -e "${GREEN}✓ 前端服务运行中${NC}"
    else
        echo -e "${YELLOW}⚠ 前端服务未运行${NC}"
    fi
    
    echo ""
    echo "完整快照请查看: $snapshot1"
}

# 主流程
case "${1:-snapshot}" in
    snapshot) generate_snapshot ;;
    view) restore_snapshot "$2" ;;
    diff) diff_snapshot "$2" "$3" ;;
    *) 
        echo "用法: $0 {snapshot|view [path]|diff [path]}"
        echo ""
        echo "  snapshot - 生成当前环境快照"
        echo "  view     - 查看快照内容"
        echo "  diff     - 比对快照变化"
        ;;
esac
