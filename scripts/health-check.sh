#!/usr/bin/env bash
# ============================================================
# 健康检查脚本
# 自动化检查所有服务、数据库、依赖项的健康状态
# ============================================================

set -euo pipefail

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/environment/server-prod.toml"
APP_DIR="/opt/app"
STATE_DIR="$APP_DIR/state"
LOG_DIR="$APP_DIR/shared/logs"
REPORT_FILE="$STATE_DIR/health-report.json"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 状态计数
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0
WARNINGS=0

# 检查结果数组
declare -a CHECK_RESULTS=()

# 日志函数
log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }
log_debug() { echo -e "${CYAN}[ℹ]${NC} $1"; }

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

# 添加检查结果
add_check() {
    local name="$1"
    local status="$2"  # PASS, FAIL, WARN
    local message="$3"
    local details="${4:-}"
    
    TOTAL_CHECKS=$((TOTAL_CHECKS + 1))
    
    case "$status" in
        PASS)
            PASSED_CHECKS=$((PASSED_CHECKS + 1))
            log_info "$name: $message"
            ;;
        FAIL)
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
            log_error "$name: $message"
            ;;
        WARN)
            WARNINGS=$((WARNINGS + 1))
            log_warn "$name: $message"
            ;;
    esac
    
    # 添加到结果数组
    CHECK_RESULTS+=("{\"name\":\"$name\",\"status\":\"$status\",\"message\":\"$message\",\"details\":\"$details\"}")
}

# 检查端口占用
check_port() {
    local port=$1
    local service=$2
    
    if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":${port} " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        local proc=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        add_check "$service 端口" "PASS" "端口 $port 正常 (PID: $pid, $proc)" "pid:$pid,process:$proc"
        return 0
    else
        add_check "$service 端口" "FAIL" "端口 $port 未监听" ""
        return 1
    fi
}

# 检查 HTTP 服务
check_http() {
    local url=$1
    local service=$2
    local expected_code=${3:-200}
    local timeout=${4:-5}
    
    local http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "$url" 2>/dev/null || echo "000")
    
    if [[ "$http_code" == "$expected_code" || "$http_code" == "200" ]]; then
        add_check "$service HTTP" "PASS" "HTTP $http_code" "url:$url"
        return 0
    elif [[ "$http_code" == "000" ]]; then
        add_check "$service HTTP" "FAIL" "无法连接" "url:$url"
        return 1
    else
        add_check "$service HTTP" "FAIL" "HTTP $http_code (期望 $expected_code)" "url:$url"
        return 1
    fi
}

# 检查文件系统
check_filesystem() {
    local path=$1
    local name=$2
    local min_size=${3:-0}
    
    if [[ ! -e "$path" ]]; then
        add_check "$name" "FAIL" "路径不存在: $path" ""
        return 1
    fi
    
    if [[ -f "$path" ]]; then
        local size=$(stat -c%s "$path" 2>/dev/null || stat -f%z "$path" 2>/dev/null || echo "0")
        if [[ $size -lt $min_size ]]; then
            add_check "$name" "WARN" "文件过小: $size bytes (最小 $min_size)" "path:$path,size:$size"
            return 1
        fi
        add_check "$name" "PASS" "文件正常 ($size bytes)" "path:$path"
    elif [[ -d "$path" ]]; then
        add_check "$name" "PASS" "目录存在" "path:$path"
    fi
    
    return 0
}

# 检查 Python 环境
check_python() {
    local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
    
    if [[ ! -x "$py_path" ]]; then
        add_check "Python 环境" "FAIL" "Python 不存在或不可执行: $py_path" ""
        return 1
    fi
    
    local version=$($py_path --version 2>&1 | cut -d' ' -f2)
    add_check "Python 版本" "PASS" "$version" "path:$py_path"
    
    # 检查关键包
    local packages=("flask" "requests" "sqlite3")
    for pkg in "${packages[@]}"; do
        if $py_path -c "import $pkg" 2>/dev/null; then
            add_check "Python 包: $pkg" "PASS" "已安装" ""
        else
            add_check "Python 包: $pkg" "WARN" "未安装" ""
        fi
    done
    
    return 0
}

# 检查数据库
check_database() {
    local db_dir=$(get_config "paths" "shared_data" || echo "$APP_DIR/shared/data")
    local db_file=$(get_config "database" "file" || echo "architecture.db")
    local db_path="$db_dir/$db_file"
    local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
    
    if [[ ! -f "$db_path" ]]; then
        add_check "数据库文件" "FAIL" "不存在: $db_path" ""
        return 1
    fi
    
    local size=$(stat -c%s "$db_path" 2>/dev/null || stat -f%z "$db_path" 2>/dev/null || echo "0")
    if [[ $size -eq 0 ]]; then
        add_check "数据库文件" "FAIL" "文件为空" "path:$db_path"
        return 1
    fi
    
    add_check "数据库文件" "PASS" "存在 ($size bytes)" "path:$db_path"
    
    # 检查数据库可访问性
    local tables=$($py_path -c "
import sqlite3
try:
    conn = sqlite3.connect('$db_path')
    cursor = conn.cursor()
    cursor.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")
    tables = [t[0] for t in cursor.fetchall()]
    conn.close()
    print(len(tables))
except Exception as e:
    print('ERROR:' + str(e))
" 2>/dev/null)
    
    if [[ "$tables" == ERROR:* ]]; then
        add_check "数据库访问" "FAIL" "${tables#ERROR:}" ""
        return 1
    elif [[ "$tables" -eq 0 ]]; then
        add_check "数据库表" "WARN" "数据库为空，没有表" ""
    else
        add_check "数据库表" "PASS" "$tables 个表" ""
    fi
    
    return 0
}

# 检查磁盘空间
check_disk_space() {
    local threshold=90
    
    local usage=$(df / 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
    
    if [[ -z "$usage" ]]; then
        add_check "磁盘空间" "WARN" "无法获取磁盘使用率" ""
        return 1
    fi
    
    if [[ $usage -ge $threshold ]]; then
        add_check "磁盘空间" "FAIL" "使用率 ${usage}% (阈值 ${threshold}%)" "usage:$usage%"
        return 1
    elif [[ $usage -ge 80 ]]; then
        add_check "磁盘空间" "WARN" "使用率 ${usage}%" "usage:$usage%"
    else
        add_check "磁盘空间" "PASS" "使用率 ${usage}%" "usage:$usage%"
    fi
    
    return 0
}

# 检查内存
check_memory() {
    local mem_info=$(free -m 2>/dev/null | awk 'NR==2{printf "%.1f", $3*100/$2}')
    
    if [[ -z "$mem_info" ]]; then
        add_check "内存使用" "WARN" "无法获取内存信息" ""
        return 1
    fi
    
    if (( $(echo "$mem_info > 90" | bc -l) )); then
        add_check "内存使用" "WARN" "使用率 ${mem_info}%" "usage:${mem_info}%"
    else
        add_check "内存使用" "PASS" "使用率 ${mem_info}%" "usage:${mem_info}%"
    fi
    
    return 0
}

# 检查当前版本
check_current_version() {
    if [[ -L "$APP_DIR/current" ]]; then
        local version=$(readlink "$APP_DIR/current" | xargs basename)
        add_check "当前版本" "PASS" "$version" "path:$APP_DIR/current"
    else
        add_check "当前版本" "FAIL" "current 链接不存在" ""
        return 1
    fi
    
    return 0
}

# 检查 API 端点
check_api_endpoints() {
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local base_url="http://localhost:$backend_port"
    
    # 检查健康检查端点
    check_http "$base_url/api/v1/health" "API 健康检查" 200
    
    # 检查 Schema API
    check_http "$base_url/api/v1/schema" "Schema API" 200
    
    # 检查 Manage API
    check_http "$base_url/api/v1/manage/product" "Manage API" 200
    
    return 0
}

# 生成 JSON 报告
generate_report() {
    mkdir -p "$STATE_DIR"
    
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local overall_status="HEALTHY"
    
    if [[ $FAILED_CHECKS -gt 0 ]]; then
        overall_status="UNHEALTHY"
    elif [[ $WARNINGS -gt 0 ]]; then
        overall_status="DEGRADED"
    fi
    
    # 构建 JSON
    local checks_json="["
    local first=true
    for result in "${CHECK_RESULTS[@]}"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            checks_json="$checks_json,"
        fi
        checks_json="$checks_json$result"
    done
    checks_json="$checks_json]"
    
    cat > "$REPORT_FILE" << EOF
{
    "timestamp": "$timestamp",
    "overall_status": "$overall_status",
    "summary": {
        "total": $TOTAL_CHECKS,
        "passed": $PASSED_CHECKS,
        "failed": $FAILED_CHECKS,
        "warnings": $WARNINGS
    },
    "checks": $checks_json
}
EOF
    
    log_debug "报告已保存: $REPORT_FILE"
}

# 显示摘要
show_summary() {
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  健康检查摘要"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  总检查数: $TOTAL_CHECKS"
    echo -e "  通过: ${GREEN}$PASSED_CHECKS${NC}"
    echo -e "  失败: ${RED}$FAILED_CHECKS${NC}"
    echo -e "  警告: ${YELLOW}$WARNINGS${NC}"
    echo ""
    
    if [[ $FAILED_CHECKS -gt 0 ]]; then
        echo -e "  整体状态: ${RED}❌ 不健康${NC}"
        echo ""
        return 1
    elif [[ $WARNINGS -gt 0 ]]; then
        echo -e "  整体状态: ${YELLOW}⚠️ 降级${NC}"
        echo ""
        return 0
    else
        echo -e "  整体状态: ${GREEN}✅ 健康${NC}"
        echo ""
        return 0
    fi
}

# 显示帮助
show_help() {
    cat << EOF
用法: $(basename "$0") [选项]

健康检查脚本 - 自动化检查所有服务、数据库、依赖项的健康状态

选项:
    -h, --help          显示帮助信息
    -q, --quiet         静默模式，只输出结果
    -j, --json          只输出 JSON 报告
    -f, --fail-fast     遇到第一个失败时退出
    -c, --check <type>  只检查指定类型 (services|database|filesystem|all)

示例:
    $(basename "$0")                    # 执行完整健康检查
    $(basename "$0") -q                 # 静默模式
    $(basename "$0") -j                 # 输出 JSON 报告
    $(basename "$0") -c services        # 只检查服务

EOF
}

# 主函数
main() {
    local quiet="false"
    local json_only="false"
    local fail_fast="false"
    local check_type="all"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -q|--quiet)
                quiet="true"
                shift
                ;;
            -j|--json)
                json_only="true"
                shift
                ;;
            -f|--fail-fast)
                fail_fast="true"
                shift
                ;;
            -c|--check)
                check_type="$2"
                shift 2
                ;;
            -*)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
            *)
                shift
                ;;
        esac
    done
    
    # 确保日志目录存在
    mkdir -p "$LOG_DIR"
    mkdir -p "$STATE_DIR"
    
    if [[ "$json_only" != "true" ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  系统健康检查"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
    fi
    
    # 执行检查
    if [[ "$check_type" == "all" || "$check_type" == "filesystem" ]]; then
        [[ "$quiet" != "true" ]] && log_step "检查文件系统..."
        check_filesystem "$APP_DIR" "应用目录"
        check_filesystem "$APP_DIR/shared/data" "数据目录"
        check_filesystem "$APP_DIR/shared/logs" "日志目录"
    fi
    
    if [[ "$check_type" == "all" || "$check_type" == "services" ]]; then
        [[ "$quiet" != "true" ]] && log_step "检查服务状态..."
        
        # 端口检查
        local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
        local backend_port=$(get_config "services.backend" "port" || echo "5001")
        local admin_port=$(get_config "services.admin" "port" || echo "8080")
        
        check_port "$frontend_port" "前端服务"
        check_port "$backend_port" "后端服务"
        check_port "$admin_port" "Admin服务"
        
        # HTTP 检查
        check_http "http://localhost:$frontend_port/" "前端 HTTP"
        check_http "http://localhost:$backend_port/api/v1/health" "后端 HTTP"
        check_http "http://localhost:$admin_port/admin" "Admin HTTP" 200
        
        # API 端点检查
        check_api_endpoints
    fi
    
    if [[ "$check_type" == "all" || "$check_type" == "database" ]]; then
        [[ "$quiet" != "true" ]] && log_step "检查数据库..."
        check_database
    fi
    
    if [[ "$check_type" == "all" ]]; then
        [[ "$quiet" != "true" ]] && log_step "检查环境..."
        check_python
        check_current_version
        check_disk_space
        check_memory
    fi
    
    # 生成报告
    generate_report
    
    # 输出结果
    if [[ "$json_only" == "true" ]]; then
        cat "$REPORT_FILE"
    else
        show_summary
    fi
    
    # 返回状态码
    if [[ $FAILED_CHECKS -gt 0 ]]; then
        exit 1
    else
        exit 0
    fi
}

# 运行主函数
main "$@"
