#!/usr/bin/env bash
# ============================================================
# 增强版环境快照脚本
# 支持变更检测、历史对比、自动告警
# ============================================================

set -euo pipefail

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/environment/server-prod.toml"
APP_DIR="/opt/app"
STATE_DIR="$APP_DIR/state"
SNAPSHOT_DIR="$STATE_DIR/snapshots"
CURRENT_SNAPSHOT="$STATE_DIR/environment-snapshot.json"
HISTORY_FILE="$STATE_DIR/snapshot-history.log"
ALERT_THRESHOLD_FILE="$STATE_DIR/alert-thresholds.conf"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 日志
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_debug() { echo -e "${CYAN}[DEBUG]${NC} $1"; }

# 确保目录存在
mkdir -p "$SNAPSHOT_DIR"
mkdir -p "$STATE_DIR"

# 从配置读取值
get_config() {
    local section="$1"
    local key="$2"
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        echo ""
        return
    fi
    
    awk -F'=' -v section="[$section]" '
        BEGIN { in_section=0 }
        /^\[/ { in_section = ($0 == section) }
        in_section && $1 ~ /^'"$key"'$/ {
            gsub(/^[ \t]+|[ \t]+$/, "", $0)
            sub(/^'"$key"'[ \t]*=[ \t]*/, "")
            gsub(/^[ \t"]+|[ \t"]+$/, "", $0)
            print $0
            exit
        }
    ' "$CONFIG_FILE" 2>/dev/null || echo ""
}

# 获取 Python 信息
get_python_info() {
    local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
    
    if [[ ! -x "$py_path" ]]; then
        echo '{"version": "not_found", "path": "'"$py_path"'", "packages": []}'
        return
    fi
    
    local version=$($py_path --version 2>&1 | cut -d' ' -f2)
    local prefix=$($py_path -c "import sys; print(sys.prefix)" 2>/dev/null || echo "unknown")
    
    # 获取关键包版本
    local packages=$($py_path -c "
import json
try:
    import pkg_resources
    pkgs = []
    for p in ['flask', 'requests', 'pyyaml', 'sqlite3']:
        try:
            v = pkg_resources.get_distribution(p).version
            pkgs.append({'name': p, 'version': v})
        except:
            pkgs.append({'name': p, 'version': 'not_installed'})
    print(json.dumps(pkgs))
except:
    print('[]')
" 2>/dev/null || echo "[]")
    
    cat << EOF
{
    "version": "$version",
    "path": "$py_path",
    "prefix": "$prefix",
    "packages": $packages
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
    local uptime="null"
    
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        running=true
        pid=$(netstat -tlnp 2>/dev/null | grep ":${port} " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        if [[ -n "$pid" && "$pid" != "null" ]]; then
            proc_name=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
            uptime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ' || echo "unknown")
        fi
    fi
    
    cat << EOF
{
    "name": "$service_name",
    "port": $port,
    "running": $running,
    "pid": ${pid:-null},
    "process": "$proc_name",
    "uptime": "$uptime"
}
EOF
}

# 获取目录信息
get_directory_info() {
    local base_dir=$(get_config "paths" "app_root" || echo "/opt/app")
    
    local dirs=()
    for dir in "$base_dir" "$base_dir/shared" "$base_dir/shared/data" "$base_dir/shared/logs" "$base_dir/releases" "$base_dir/backups"; do
        local exists="false"
        local size="0"
        local mtime="null"
        
        if [[ -d "$dir" ]]; then
            exists="true"
            size=$(du -sb "$dir" 2>/dev/null | cut -f1 || echo "0")
            mtime=$(stat -c %Y "$dir" 2>/dev/null || echo "0")
        fi
        
        dirs+=("{\"path\":\"$dir\",\"exists\":$exists,\"size_bytes\":$size,\"mtime\":$mtime}")
    done
    
    echo "[$(IFS=,; echo "${dirs[*]}")]"
}

# 获取数据库信息
get_database_info() {
    local db_dir=$(get_config "paths" "shared_data" || echo "/opt/app/shared/data")
    local db_file=$(get_config "database" "file" || echo "architecture.db")
    local db_path="$db_dir/$db_file"
    
    local exists=false
    local size=0
    local tables="[]"
    local version="unknown"
    local record_count=0
    
    if [[ -f "$db_path" ]]; then
        exists=true
        size=$(stat -c%s "$db_path" 2>/dev/null || stat -f%z "$db_path" 2>/dev/null || echo "0")
        
        local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
        
        # 获取表信息
        local db_data=$($py_path -c "
import sqlite3
import json
try:
    conn = sqlite3.connect('$db_path')
    cursor = conn.cursor()
    
    # 获取所有表
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\")
    tables = [t[0] for t in cursor.fetchall()]
    
    # 获取记录数
    total_records = 0
    for table in tables:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            total_records += count
        except:
            pass
    
    # 获取版本
    try:
        cursor.execute('SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1')
        result = cursor.fetchone()
        schema_version = result[0] if result else 'init'
    except:
        schema_version = 'unknown'
    
    conn.close()
    print(json.dumps({'tables': tables, 'record_count': total_records, 'version': schema_version}))
except Exception as e:
    print(json.dumps({'tables': [], 'record_count': 0, 'version': 'error: ' + str(e)}))
" 2>/dev/null)
        
        tables=$(echo "$db_data" | python3 -c "import sys,json; print(json.dumps(json.load(sys.stdin)['tables']))" 2>/dev/null || echo "[]")
        record_count=$(echo "$db_data" | python3 -c "import sys,json; print(json.load(sys.stdin)['record_count'])" 2>/dev/null || echo "0")
        version=$(echo "$db_data" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "unknown")
    fi
    
    cat << EOF
{
    "path": "$db_path",
    "exists": $exists,
    "size_bytes": $size,
    "tables": $tables,
    "table_count": $(echo "$tables" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0"),
    "record_count": $record_count,
    "schema_version": "$version"
}
EOF
}

# 获取当前版本信息
get_version_info() {
    local current=""
    local previous=""
    
    if [[ -L "$APP_DIR/current" ]]; then
        current=$(readlink "$APP_DIR/current" | xargs basename)
    fi
    
    # 获取上一个版本
    if [[ -d "$APP_DIR/releases" ]]; then
        previous=$(ls -1td "$APP_DIR/releases"/v* 2>/dev/null | grep -v "$current" | head -1 | xargs basename 2>/dev/null || echo "")
    fi
    
    cat << EOF
{
    "current": "$current",
    "previous": "$previous",
    "current_path": "$APP_DIR/current",
    "target_path": "$APP_DIR/releases/$current"
}
EOF
}

# 生成快照
generate_snapshot() {
    log_step "生成环境快照..."
    
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local snapshot_id=$(date +"%Y%m%d_%H%M%S")
    local snapshot_file="$SNAPSHOT_DIR/snapshot_${snapshot_id}.json"
    
    # 获取各项信息
    local python_info=$(get_python_info)
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local admin_port=$(get_config "services.admin" "port" || echo "8080")
    local frontend_status=$(get_service_status "$frontend_port" "frontend")
    local backend_status=$(get_service_status "$backend_port" "backend")
    local admin_status=$(get_service_status "$admin_port" "admin")
    local dir_info=$(get_directory_info)
    local db_info=$(get_database_info)
    local version_info=$(get_version_info)
    
    # 磁盘信息
    local disk_total=$(df -BG / 2>/dev/null | awk 'NR==2 {print $2}' | tr -d 'G' || echo "0")
    local disk_used=$(df -BG / 2>/dev/null | awk 'NR==2 {print $3}' | tr -d 'G' || echo "0")
    local disk_avail=$(df -BG / 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G' || echo "0")
    local disk_usage=$(df / 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}' || echo "0")
    
    # 内存信息
    local mem_total=$(free -m 2>/dev/null | awk 'NR==2 {print $2}' || echo "0")
    local mem_used=$(free -m 2>/dev/null | awk 'NR==2 {print $3}' || echo "0")
    local mem_avail=$(free -m 2>/dev/null | awk 'NR==2 {print $7}' || echo "0")
    
    # 组装完整快照
    cat > "$snapshot_file" << EOF
{
    "snapshot_id": "$snapshot_id",
    "timestamp": "$timestamp",
    "hostname": "$(hostname)",
    "os": "$(cat /etc/centos-release 2>/dev/null || cat /etc/redhat-release 2>/dev/null || echo 'unknown')",
    "kernel": "$(uname -r)",
    "uptime_seconds": $(cut -d. -f1 /proc/uptime 2>/dev/null || echo 0),
    
    "version": $version_info,
    
    "python": $python_info,
    
    "services": {
        "frontend": $frontend_status,
        "backend": $backend_status,
        "admin": $admin_status
    },
    
    "directories": $dir_info,
    
    "database": $db_info,
    
    "resources": {
        "disk": {
            "total_gb": $disk_total,
            "used_gb": $disk_used,
            "available_gb": $disk_avail,
            "usage_percent": $disk_usage
        },
        "memory": {
            "total_mb": $mem_total,
            "used_mb": $mem_used,
            "available_mb": $mem_avail
        },
        "cpu_cores": $(nproc 2>/dev/null || echo 1)
    },
    
    "network": {
        "hostname": "$(hostname -f 2>/dev/null || hostname)",
        "ip_addresses": [
            $(ip addr show 2>/dev/null | grep "inet " | awk '{print "\""$2"\""}' | tr '\n' ',' | sed 's/,$//')
        ]
    }
}
EOF
    
    # 更新当前快照链接
    cp "$snapshot_file" "$CURRENT_SNAPSHOT"
    
    # 记录历史
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 快照生成: $snapshot_id" >> "$HISTORY_FILE"
    
    log_info "快照已保存: $snapshot_file"
    
    # 输出摘要
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  环境快照摘要"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  快照ID: $snapshot_id"
    echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "  服务器: $(hostname)"
    echo ""
    echo "  版本: $(echo "$version_info" | python3 -c "import sys,json; print(json.load(sys.stdin)['current'])" 2>/dev/null || echo "unknown")"
    echo "  Python: $(echo "$python_info" | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])" 2>/dev/null || echo "unknown")"
    echo ""
    echo "  服务状态:"
    echo "    前端 ($frontend_port): $(echo "$frontend_status" | python3 -c "import sys,json; print('运行中' if json.load(sys.stdin)['running'] else '未运行')" 2>/dev/null)"
    echo "    后端 ($backend_port): $(echo "$backend_status" | python3 -c "import sys,json; print('运行中' if json.load(sys.stdin)['running'] else '未运行')" 2>/dev/null)"
    echo "    Admin ($admin_port): $(echo "$admin_status" | python3 -c "import sys,json; print('运行中' if json.load(sys.stdin)['running'] else '未运行')" 2>/dev/null)"
    echo ""
    echo "  数据库: $(echo "$db_info" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"{d['table_count']} 个表, {d['record_count']} 条记录\")" 2>/dev/null)"
    echo "  磁盘使用: ${disk_usage}% (${disk_used}GB / ${disk_total}GB)"
    echo ""
    
    # 检查告警阈值
    check_alerts "$snapshot_file"
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

# 检查告警
check_alerts() {
    local snapshot_file="$1"
    
    # 默认阈值
    local disk_threshold=90
    local mem_threshold=90
    
    # 读取自定义阈值
    if [[ -f "$ALERT_THRESHOLD_FILE" ]]; then
        source "$ALERT_THRESHOLD_FILE"
    fi
    
    local alerts=()
    
    # 检查磁盘使用率
    local disk_usage=$(cat "$snapshot_file" | python3 -c "import sys,json; print(json.load(sys.stdin)['resources']['disk']['usage_percent'])" 2>/dev/null || echo "0")
    if [[ $disk_usage -ge $disk_threshold ]]; then
        alerts+=("磁盘使用率过高: ${disk_usage}% (阈值: ${disk_threshold}%)")
    fi
    
    # 检查服务状态
    local services=("frontend" "backend" "admin")
    for svc in "${services[@]}"; do
        local running=$(cat "$snapshot_file" | python3 -c "import sys,json; print(json.load(sys.stdin)['services']['$svc']['running'])" 2>/dev/null || echo "false")
        if [[ "$running" != "True" && "$running" != "true" ]]; then
            alerts+=("服务未运行: $svc")
        fi
    done
    
    # 检查数据库
    local db_exists=$(cat "$snapshot_file" | python3 -c "import sys,json; print(json.load(sys.stdin)['database']['exists'])" 2>/dev/null || echo "false")
    if [[ "$db_exists" != "True" && "$db_exists" != "true" ]]; then
        alerts+=("数据库文件不存在")
    fi
    
    # 显示告警
    if [[ ${#alerts[@]} -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  检测到 ${#alerts[@]} 个告警:${NC}"
        for alert in "${alerts[@]}"; do
            echo -e "  ${YELLOW}! $alert${NC}"
        done
        echo ""
        
        # 记录告警
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 告警: ${#alerts[@]} 个" >> "$HISTORY_FILE"
        for alert in "${alerts[@]}"; do
            echo "  - $alert" >> "$HISTORY_FILE"
        done
    fi
}

# 查看快照
view_snapshot() {
    local snapshot_file="${1:-$CURRENT_SNAPSHOT}"
    
    if [[ ! -f "$snapshot_file" ]]; then
        log_error "快照文件不存在: $snapshot_file"
        exit 1
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  快照详情"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    cat "$snapshot_file" | python3 -m json.tool 2>/dev/null || cat "$snapshot_file"
    
    echo ""
}

# 列出历史快照
list_snapshots() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  快照历史"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [[ ! -d "$SNAPSHOT_DIR" ]]; then
        log_warn "快照目录不存在"
        return 1
    fi
    
    local count=0
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        
        local filename=$(basename "$file")
        local mtime=$(stat -c %y "$file" 2>/dev/null | cut -d' ' -f1,2 | cut -d'.' -f1)
        local size=$(du -h "$file" 2>/dev/null | cut -f1)
        local is_current=""
        
        if [[ "$file" == "$CURRENT_SNAPSHOT" ]]; then
            is_current="${GREEN}(当前)${NC}"
        fi
        
        printf "  %-30s %12s  %s  %b\n" "$filename" "$size" "$mtime" "$is_current"
        ((count++))
    done < <(ls -1td "$SNAPSHOT_DIR"/snapshot_*.json 2>/dev/null)
    
    echo ""
    echo "共 $count 个快照"
    echo ""
}

# 对比快照
diff_snapshots() {
    local snapshot1="$1"
    local snapshot2="${2:-$CURRENT_SNAPSHOT}"
    
    if [[ ! -f "$snapshot1" ]]; then
        log_error "快照文件不存在: $snapshot1"
        exit 1
    fi
    
    if [[ ! -f "$snapshot2" ]]; then
        log_error "快照文件不存在: $snapshot2"
        exit 1
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  快照对比"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  基准: $(basename "$snapshot1")"
    echo "  对比: $(basename "$snapshot2")"
    echo ""
    
    # 使用 Python 进行对比
    python3 << EOF
import json
import sys

def load_snapshot(path):
    with open(path, 'r') as f:
        return json.load(f)

def compare_values(old, new, path=""):
    changes = []
    
    if type(old) != type(new):
        changes.append(f"{path}: 类型变化 {type(old).__name__} -> {type(new).__name__}")
        return changes
    
    if isinstance(old, dict):
        all_keys = set(old.keys()) | set(new.keys())
        for key in all_keys:
            new_path = f"{path}.{key}" if path else key
            if key not in old:
                changes.append(f"{new_path}: 新增")
            elif key not in new:
                changes.append(f"{new_path}: 删除")
            else:
                changes.extend(compare_values(old[key], new[key], new_path))
    elif isinstance(old, list):
        if len(old) != len(new):
            changes.append(f"{path}: 长度变化 {len(old)} -> {len(new)}")
        else:
            for i, (o, n) in enumerate(zip(old, new)):
                changes.extend(compare_values(o, n, f"{path}[{i}]"))
    elif old != new:
        changes.append(f"{path}: {old} -> {new}")
    
    return changes

try:
    old = load_snapshot("$snapshot1")
    new = load_snapshot("$snapshot2")
    
    changes = compare_values(old, new)
    
    if changes:
        print("检测到以下变化:")
        print("")
        for change in changes:
            print(f"  • {change}")
    else:
        print("没有检测到变化")
        
except Exception as e:
    print(f"对比失败: {e}", file=sys.stderr)
    sys.exit(1)
EOF
    
    echo ""
}

# 清理旧快照
cleanup_snapshots() {
    local keep_count=${1:-10}
    
    log_step "清理旧快照 (保留最近 $keep_count 个)..."
    
    local count=0
    while IFS= read -r file; do
        [[ -z "$file" ]] && continue
        ((count++))
        
        if [[ $count -gt $keep_count ]]; then
            rm -f "$file"
            log_info "删除: $(basename "$file")"
        fi
    done < <(ls -1td "$SNAPSHOT_DIR"/snapshot_*.json 2>/dev/null)
    
    log_info "清理完成"
}

# 显示帮助
show_help() {
    cat << EOF
用法: $(basename "$0") [命令] [选项]

增强版环境快照脚本 - 支持变更检测、历史对比、自动告警

命令:
    snapshot                    生成当前环境快照
    view [file]                 查看快照内容
    list                        列出所有快照
    diff <file1> [file2]        对比两个快照
    cleanup [count]             清理旧快照 (默认保留10个)
    schedule                    设置定时快照 (crontab)

选项:
    -h, --help                  显示帮助信息

示例:
    $(basename "$0") snapshot                       # 生成快照
    $(basename "$0") view                           # 查看最新快照
    $(basename "$0") list                           # 列出所有快照
    $(basename "$0") diff snapshot_20240428.json    # 对比当前与历史快照
    $(basename "$0") cleanup 5                      # 只保留最近5个快照

EOF
}

# 设置定时任务
setup_schedule() {
    log_step "设置定时快照..."
    
    # 检查是否已有定时任务
    if crontab -l 2>/dev/null | grep -q "snapshot-enhanced.sh"; then
        log_warn "定时任务已存在"
        echo ""
        echo "当前定时任务:"
        crontab -l | grep "snapshot-enhanced.sh"
        echo ""
        read -p "是否重新设置? (y/n): " confirm
        [[ "$confirm" != "y" ]] && return
    fi
    
    echo ""
    echo "选择快照频率:"
    echo "  1) 每小时"
    echo "  2) 每6小时"
    echo "  3) 每天"
    echo "  4) 每周"
    echo "  5) 自定义"
    echo ""
    read -p "选择 (1-5): " choice
    
    local cron_expr=""
    case $choice in
        1) cron_expr="0 * * * *" ;;
        2) cron_expr="0 */6 * * *" ;;
        3) cron_expr="0 0 * * *" ;;
        4) cron_expr="0 0 * * 0" ;;
        5) 
            read -p "输入 cron 表达式 (如 '0 2 * * *'): " cron_expr
            ;;
        *) 
            log_error "无效选择"
            return 1
            ;;
    esac
    
    local script_path="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
    
    # 添加定时任务
    (crontab -l 2>/dev/null; echo "$cron_expr $script_path snapshot >> $LOG_DIR/snapshot-cron.log 2>&1") | crontab -
    
    log_info "定时任务已设置: $cron_expr"
}

# 主流程
main() {
    local command="${1:-snapshot}"
    
    case "$command" in
        snapshot)
            generate_snapshot
            ;;
        view)
            view_snapshot "${2:-}"
            ;;
        list)
            list_snapshots
            ;;
        diff)
            if [[ -z "${2:-}" ]]; then
                log_error "请提供基准快照文件"
                show_help
                exit 1
            fi
            diff_snapshots "$2" "${3:-$CURRENT_SNAPSHOT}"
            ;;
        cleanup)
            cleanup_snapshots "${2:-10}"
            ;;
        schedule)
            setup_schedule
            ;;
        -h|--help|help)
            show_help
            exit 0
            ;;
        *)
            log_error "未知命令: $command"
            show_help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
