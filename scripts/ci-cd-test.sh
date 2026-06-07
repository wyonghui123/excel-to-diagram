#!/usr/bin/env bash
# ============================================================
# CI/CD 自动化测试脚本
# 用于集成到部署流程的自动化测试
# ============================================================

set -euo pipefail

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/environment/server-prod.toml"
APP_DIR="/opt/app"
STATE_DIR="$APP_DIR/state"
TEST_RESULT_DIR="$STATE_DIR/test-results"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
REPORT_FILE="$TEST_RESULT_DIR/test-report-$TIMESTAMP.json"
HTML_REPORT_FILE="$TEST_RESULT_DIR/test-report-$TIMESTAMP.html"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 测试统计
TESTS_TOTAL=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

# 测试结果数组
declare -a TEST_RESULTS=()

# 日志函数
log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_pass() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_step() { echo -e "${BLUE}[TEST]${NC} $1"; }
log_debug() { echo -e "${CYAN}[DEBUG]${NC} $1"; }

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

# 记录测试结果
record_test() {
    local test_name="$1"
    local status="$2"
    local message="${3:-}"
    local duration="${4:-0}"
    
    TESTS_TOTAL=$((TESTS_TOTAL + 1))
    
    case "$status" in
        PASS)
            TESTS_PASSED=$((TESTS_PASSED + 1))
            log_pass "$test_name"
            ;;
        FAIL)
            TESTS_FAILED=$((TESTS_FAILED + 1))
            log_fail "$test_name: $message"
            ;;
        SKIP)
            TESTS_SKIPPED=$((TESTS_SKIPPED + 1))
            log_warn "$test_name: SKIPPED - $message"
            ;;
    esac
    
    TEST_RESULTS+=("{\"name\":\"$test_name\",\"status\":\"$status\",\"message\":\"$message\",\"duration\":\"$duration\"}")
}

# 获取HTTP状态码
get_http_code() {
    local url="$1"
    local timeout="${2:-10}"
    curl -s -o /dev/null -w "%{http_code}" --max-time "$timeout" "$url" 2>/dev/null || echo "000"
}

# ============================================================
# 测试：服务端口检查
# ============================================================
test_service_ports() {
    log_step "测试服务端口..."
    
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local admin_port=$(get_config "services.admin" "port" || echo "8080")
    
    # 测试前端端口
    if netstat -tlnp 2>/dev/null | grep -q ":${frontend_port} "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":${frontend_port} " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        record_test "前端服务端口 ($frontend_port)" "PASS" "端口监听中, PID: $pid"
    else
        record_test "前端服务端口 ($frontend_port)" "FAIL" "端口未监听"
    fi
    
    # 测试后端端口
    if netstat -tlnp 2>/dev/null | grep -q ":${backend_port} "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":${backend_port} " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        record_test "后端服务端口 ($backend_port)" "PASS" "端口监听中, PID: $pid"
    else
        record_test "后端服务端口 ($backend_port)" "FAIL" "端口未监听"
    fi
    
    # 测试Admin端口
    if netstat -tlnp 2>/dev/null | grep -q ":${admin_port} "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":${admin_port} " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        record_test "Admin服务端口 ($admin_port)" "PASS" "端口监听中, PID: $pid"
    else
        record_test "Admin服务端口 ($admin_port)" "FAIL" "端口未监听"
    fi
}

# ============================================================
# 测试：HTTP端点检查
# ============================================================
test_http_endpoints() {
    log_step "测试HTTP端点..."
    
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local admin_port=$(get_config "services.admin" "port" || echo "8080")
    local backend_host="localhost"
    
    # 测试前端首页
    local http_code=$(get_http_code "http://${backend_host}:${frontend_port}/")
    if [[ "$http_code" == "200" ]]; then
        record_test "前端首页访问" "PASS" "HTTP $http_code"
    else
        record_test "前端首页访问" "FAIL" "期望200，实际$http_code"
    fi
    
    # 测试后端健康检查
    http_code=$(get_http_code "http://${backend_host}:${backend_port}/api/v1/health")
    if [[ "$http_code" == "200" ]]; then
        record_test "后端健康检查端点" "PASS" "HTTP $http_code"
    else
        record_test "后端健康检查端点" "FAIL" "期望200，实际$http_code"
    fi
    
    # 测试Schema API
    http_code=$(get_http_code "http://${backend_host}:${backend_port}/api/v1/schema")
    if [[ "$http_code" == "200" ]]; then
        record_test "Schema API端点" "PASS" "HTTP $http_code"
    else
        record_test "Schema API端点" "FAIL" "期望200，实际$http_code"
    fi
    
    # 测试Admin页面
    http_code=$(get_http_code "http://${backend_host}:${admin_port}/admin")
    if [[ "$http_code" == "200" || "$http_code" == "302" ]]; then
        record_test "Admin管理页面" "PASS" "HTTP $http_code"
    else
        record_test "Admin管理页面" "FAIL" "期望200/302，实际$http_code"
    fi
}

# ============================================================
# 测试：API功能测试
# ============================================================
test_api_functions() {
    log_step "测试API功能..."
    
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local backend_host="localhost"
    local base_url="http://${backend_host}:${backend_port}"
    
    # 测试：获取产品列表
    local response=$(curl -s --max-time 10 "${base_url}/api/v1/product?page_size=10" 2>/dev/null || echo "")
    if [[ -n "$response" && "$response" != "{}" ]]; then
        local has_data=$(echo "$response" | grep -o '"data"' || echo "")
        if [[ -n "$has_data" ]]; then
            record_test "获取产品列表API" "PASS" "返回有效数据"
        else
            record_test "获取产品列表API" "FAIL" "返回数据格式异常"
        fi
    else
        record_test "获取产品列表API" "FAIL" "返回空数据"
    fi
    
    # 测试：获取Schema列表
    response=$(curl -s --max-time 10 "${base_url}/api/v1/schema" 2>/dev/null || echo "")
    if [[ -n "$response" ]]; then
        record_test "获取Schema列表API" "PASS" "返回有效数据"
    else
        record_test "获取Schema列表API" "FAIL" "返回空数据"
    fi
    
    # 测试：统计数据API
    response=$(curl -s --max-time 10 "${base_url}/api/v1/stats" 2>/dev/null || echo "")
    if [[ -n "$response" ]]; then
        record_test "统计数据API" "PASS" "返回有效数据"
    else
        record_test "统计数据API" "FAIL" "返回空数据"
    fi
}

# ============================================================
# 测试：数据库连接
# ============================================================
test_database() {
    log_step "测试数据库连接..."
    
    local db_dir=$(get_config "paths" "shared_data" || echo "$APP_DIR/shared/data")
    local db_file=$(get_config "database" "file" || echo "architecture.db")
    local db_path="$db_dir/$db_file"
    local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
    
    # 检查数据库文件
    if [[ ! -f "$db_path" ]]; then
        record_test "数据库文件存在" "FAIL" "文件不存在: $db_path"
        return
    fi
    
    record_test "数据库文件存在" "PASS" "文件大小: $(du -h "$db_path" | cut -f1)"
    
    # 检查数据库连接和表
    local db_check=$($py_path -c "
import sqlite3
try:
    conn = sqlite3.connect('$db_path')
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM sqlite_master WHERE type=\"table\"')
    table_count = cursor.fetchone()[0]
    conn.close()
    print('OK:' + str(table_count))
except Exception as e:
    print('ERROR:' + str(e))
" 2>/dev/null)
    
    if [[ "$db_check" == ERROR:* ]]; then
        record_test "数据库连接" "FAIL" "${db_check#ERROR:}"
    else
        record_test "数据库连接" "PASS" "连接成功"
        record_test "数据库表数量" "PASS" "共 ${db_check#OK:} 个表"
    fi
}

# ============================================================
# 测试：文件系统
# ============================================================
test_filesystem() {
    log_step "测试文件系统..."
    
    local dirs=("$APP_DIR" "$APP_DIR/shared" "$APP_DIR/shared/data" "$APP_DIR/shared/logs")
    for dir in "${dirs[@]}"; do
        if [[ -d "$dir" ]]; then
            record_test "目录存在: $(basename "$dir")" "PASS" "可访问"
        else
            record_test "目录存在: $(basename "$dir")" "FAIL" "目录不存在"
        fi
    done
    
    # 检查日志目录可写
    if [[ -w "$APP_DIR/shared/logs" ]]; then
        record_test "日志目录可写" "PASS" "权限正常"
    else
        record_test "日志目录可写" "FAIL" "无写权限"
    fi
}

# ============================================================
# 测试：资源使用
# ============================================================
test_resources() {
    log_step "测试资源使用..."
    
    local disk_usage=$(df / 2>/dev/null | awk 'NR==2 {gsub(/%/,""); print $5}')
    if [[ -n "$disk_usage" ]]; then
        if [[ $disk_usage -lt 90 ]]; then
            record_test "磁盘空间" "PASS" "使用率 ${disk_usage}%"
        elif [[ $disk_usage -lt 95 ]]; then
            record_test "磁盘空间" "SKIP" "使用率 ${disk_usage}%，警告"
        else
            record_test "磁盘空间" "FAIL" "使用率 ${disk_usage}%，严重不足"
        fi
    fi
    
    local mem_usage=$(free -m 2>/dev/null | awk 'NR==2 {printf "%.0f", $3*100/$2}')
    if [[ -n "$mem_usage" ]]; then
        if [[ $mem_usage -lt 80 ]]; then
            record_test "内存使用" "PASS" "使用率 ${mem_usage}%"
        elif [[ $mem_usage -lt 90 ]]; then
            record_test "内存使用" "SKIP" "使用率 ${mem_usage}%，警告"
        else
            record_test "内存使用" "FAIL" "使用率 ${mem_usage}%，过高"
        fi
    fi
}

# ============================================================
# 测试：版本信息
# ============================================================
test_version_info() {
    log_step "测试版本信息..."
    
    if [[ -L "$APP_DIR/current" ]]; then
        local version=$(readlink "$APP_DIR/current" | xargs basename)
        record_test "当前版本链接" "PASS" "版本: $version"
    else
        record_test "当前版本链接" "FAIL" "链接不存在"
    fi
}

# ============================================================
# 生成JSON报告
# ============================================================
generate_json_report() {
    mkdir -p "$TEST_RESULT_DIR"
    
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local duration=$(( $(date +%s) - START_TIME ))
    local overall_status="PASSED"
    
    if [[ $TESTS_FAILED -gt 0 ]]; then
        overall_status="FAILED"
    elif [[ $TESTS_SKIPPED -eq $TESTS_TOTAL ]]; then
        overall_status="SKIPPED"
    fi
    
    # 构建JSON数组
    local tests_json="["
    local first=true
    for result in "${TEST_RESULTS[@]}"; do
        if [[ "$first" == "true" ]]; then
            first=false
        else
            tests_json="$tests_json,"
        fi
        tests_json="$tests_json$result"
    done
    tests_json="$tests_json]"
    
    cat > "$REPORT_FILE" << EOF
{
    "timestamp": "$timestamp",
    "duration_seconds": $duration,
    "overall_status": "$overall_status",
    "summary": {
        "total": $TESTS_TOTAL,
        "passed": $TESTS_PASSED,
        "failed": $TESTS_FAILED,
        "skipped": $TESTS_SKIPPED
    },
    "tests": $tests_json
}
EOF
    
    log_info "JSON报告已保存: $REPORT_FILE"
}

# ============================================================
# 主函数
# ============================================================
main() {
    local quiet="false"
    local json_only="false"
    local test_type="all"
    
    START_TIME=$(date +%s)
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -h|--help)
                echo "用法: $(basename "$0") [选项]"
                echo ""
                echo "选项:"
                echo "  -h, --help          显示帮助"
                echo "  -q, --quiet         静默模式"
                echo "  -j, --json          只输出JSON"
                echo "  -t, --tests <type>  测试类型 (ports|http|api|db|fs|resource|all)"
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
            -t|--tests)
                test_type="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done
    
    mkdir -p "$TEST_RESULT_DIR"
    
    if [[ "$json_only" != "true" ]]; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  CI/CD 自动化测试"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
    fi
    
    # 执行测试
    if [[ "$test_type" == "all" || "$test_type" == "ports" ]]; then
        test_service_ports
    fi
    
    if [[ "$test_type" == "all" || "$test_type" == "http" ]]; then
        test_http_endpoints
    fi
    
    if [[ "$test_type" == "all" || "$test_type" == "api" ]]; then
        test_api_functions
    fi
    
    if [[ "$test_type" == "all" || "$test_type" == "db" ]]; then
        test_database
    fi
    
    if [[ "$test_type" == "all" || "$test_type" == "fs" ]]; then
        test_filesystem
    fi
    
    if [[ "$test_type" == "all" || "$test_type" == "resource" ]]; then
        test_resources
    fi
    
    if [[ "$test_type" == "all" ]]; then
        test_version_info
    fi
    
    # 生成报告
    generate_json_report
    
    # 输出结果
    if [[ "$json_only" == "true" ]]; then
        cat "$REPORT_FILE"
    else
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "  测试结果摘要"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "  总测试数: $TESTS_TOTAL"
        echo -e "  通过: ${GREEN}$TESTS_PASSED${NC}"
        echo -e "  失败: ${RED}$TESTS_FAILED${NC}"
        echo -e "  跳过: ${YELLOW}$TESTS_SKIPPED${NC}"
        echo ""
        
        if [[ $TESTS_FAILED -gt 0 ]]; then
            echo -e "  整体状态: ${RED}❌ 失败${NC}"
        else
            echo -e "  整体状态: ${GREEN}✅ 通过${NC}"
        fi
        
        echo ""
        echo "  报告文件: $REPORT_FILE"
        echo ""
    fi
    
    [[ $TESTS_FAILED -gt 0 ]] && exit 1 || exit 0
}

main "$@"