#!/usr/bin/env bash
# ============================================================
# 前置环境检查脚本
# 部署前全面检查环境是否符合要求
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/../config/environment/server-prod.toml"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 检查结果统计
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0
CHECKS_SKIPPED=0

# 日志函数
log_pass() { echo -e "${GREEN}[✓]${NC} $*"; ((CHECKS_PASSED++)); }
log_fail() { echo -e "${RED}[✗]${NC} $*"; ((CHECKS_FAILED++)); }
log_warn() { echo -e "${YELLOW}[!]${NC} $*"; ((CHECKS_WARNING++)); }
log_info() { echo -e "${BLUE}[i]${NC} $*"; }
log_skip() { echo -e "${BLUE}[→]${NC} $* (跳过)"; ((CHECKS_SKIPPED++)); }

# 从配置读取值
get_config() {
    local section="$1"
    local key="$2"
    
    # 简单的 TOML 解析
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

# ============================================================
# 检查1: 配置文件
# ============================================================
check_config_file() {
    log_info "检查配置文件..."
    
    if [[ ! -f "$CONFIG_FILE" ]]; then
        log_fail "配置文件不存在: $CONFIG_FILE"
        return 1
    fi
    
    log_pass "配置文件存在: $CONFIG_FILE"
    
    # 验证配置文件可读
    if grep -q "^\[metadata\]" "$CONFIG_FILE"; then
        log_pass "配置文件格式正确"
    else
        log_fail "配置文件格式错误"
        return 1
    fi
}

# ============================================================
# 检查2: 操作系统
# ============================================================
check_os() {
    log_info "检查操作系统..."
    
    if [[ -f /etc/centos-release ]]; then
        local os_version=$(cat /etc/centos-release)
        log_pass "操作系统: $os_version"
        
        if echo "$os_version" | grep -q "CentOS Linux release 7"; then
            log_pass "操作系统版本符合要求 (CentOS 7.x)"
        else
            log_warn "操作系统版本可能不兼容"
        fi
    elif [[ -f /etc/redhat-release ]]; then
        log_pass "操作系统: $(cat /etc/redhat-release)"
    else
        log_warn "无法识别操作系统类型"
    fi
}

# ============================================================
# 检查3: 磁盘空间
# ============================================================
check_disk_space() {
    log_info "检查磁盘空间..."
    
    local required_gb=2
    local available_gb
    
    if df -BG /opt &>/dev/null; then
        available_gb=$(df -BG /opt 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')
    else
        available_gb=$(df -BG / 2>/dev/null | awk 'NR==2 {print $4}' | tr -d 'G')
    fi
    
    if [[ -z "$available_gb" || ! "$available_gb" =~ ^[0-9]+$ ]]; then
        log_warn "无法检测磁盘空间"
        return
    fi
    
    if [[ $available_gb -ge $required_gb ]]; then
        log_pass "磁盘空间: ${available_gb}GB 可用 (需要 ${required_gb}GB)"
    else
        log_fail "磁盘空间不足: ${available_gb}GB 可用，需要 ${required_gb}GB"
    fi
    
    # 检查 /opt 目录是否存在
    if [[ -d /opt ]]; then
        log_pass "/opt 目录存在"
    else
        log_warn "/opt 目录不存在，将被创建"
    fi
}

# ============================================================
# 检查4: Python 环境
# ============================================================
check_python() {
    log_info "检查 Python 环境..."
    
    local expected_py_path=$(get_config "dependencies.python" "binary")
    
    # 如果配置中没有，使用默认值
    if [[ -z "$expected_py_path" ]]; then
        expected_py_path="/opt/miniconda3-py39/bin/python"
    fi
    
    if [[ ! -x "$expected_py_path" ]]; then
        log_fail "Python 未找到: $expected_py_path"
        
        # 尝试其他常见路径
        local found=false
        for alt_path in /usr/bin/python3 /usr/local/bin/python3 /opt/python3*/bin/python; do
            if [[ -x "$alt_path" ]]; then
                log_warn "找到替代 Python: $alt_path"
                log_info "建议更新配置文件中的 python.binary"
                found=true
                break
            fi
        done
        
        if [[ "$found" == "false" ]]; then
            log_fail "没有找到可用的 Python"
        fi
        return
    fi
    
    local version=$($expected_py_path --version 2>&1 | cut -d' ' -f2)
    log_pass "Python 版本: $version"
    log_pass "Python 路径: $expected_py_path"
    
    # 检查 pip
    local pip_path=$(get_config "dependencies.python" "pip")
    if [[ -z "$pip_path" ]]; then
        pip_path="${expected_py_path%/*}/pip"
    fi
    
    if [[ -x "$pip_path" ]]; then
        log_pass "pip 可用: $pip_path"
    else
        log_warn "pip 未找到: $pip_path"
    fi
    
    # 检查关键包
    local required_packages=("flask" "openpyxl")
    for pkg in "${required_packages[@]}"; do
        if $expected_py_path -c "import $pkg" 2>/dev/null; then
            local pkg_version=$($expected_py_path -c "import $pkg; print($pkg.__version__)" 2>/dev/null || echo "unknown")
            log_pass "  ✓ $pkg ($pkg_version)"
        else
            log_warn "  ! $pkg 未安装（部署时需要安装）"
        fi
    done
}

# ============================================================
# 检查5: 目录结构
# ============================================================
check_directories() {
    log_info "检查目录结构..."
    
    local expected_dirs=(
        "$(get_config "paths" "app_root" || echo "/opt/app")"
    )
    
    # 添加其他目录
    local base_dir=$(get_config "paths" "app_root" || echo "/opt/app")
    local required_dirs=(
        "$base_dir"
        "$(get_config "paths" "shared_data" || echo "$base_dir/shared/data")"
        "$(get_config "paths" "shared_logs" || echo "$base_dir/shared/logs")"
        "$(get_config "paths" "releases_dir" || echo "$base_dir/deployments")"
        "$(get_config "paths" "backup_dir" || echo "$base_dir/backups")"
    )
    
    for dir in "${required_dirs[@]}"; do
        if [[ -z "$dir" ]]; then
            continue
        fi
        
        if [[ -d "$dir" ]]; then
            log_pass "目录存在: $dir"
        else
            log_warn "目录不存在: $dir (部署时将创建)"
        fi
    done
}

# ============================================================
# 检查6: 端口状态
# ============================================================
check_ports() {
    log_info "检查端口状态..."
    
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    local required_ports=("$frontend_port" "$backend_port")
    
    for port in "${required_ports[@]}"; do
        if netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            local proc_info=$(netstat -tlnp 2>/dev/null | grep ":${port} " | head -1)
            local pid=$(echo "$proc_info" | awk '{print $7}' | cut -d'/' -f1)
            log_warn "端口 ${port} 已被占用 (PID: $pid)"
        else
            log_pass "端口 ${port} 可用"
        fi
    done
}

# ============================================================
# 检查7: 数据库
# ============================================================
check_database() {
    log_info "检查数据库..."
    
    local base_dir=$(get_config "paths" "shared_data" || echo "/opt/app/shared/data")
    local db_file=$(get_config "database" "file" || echo "architecture.db")
    local db_path="$base_dir/$db_file"
    
    if [[ -f "$db_path" ]]; then
        local size=$(du -h "$db_path" | cut -f1)
        log_pass "数据库存在: $db_path ($size)"
        
        # 验证数据库可读
        local py_path=$(get_config "dependencies.python" "binary" || echo "/opt/miniconda3-py39/bin/python")
        
        if $py_path -c "
import sqlite3
conn = sqlite3.connect('$db_path')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type=\"table\" LIMIT 5')
tables = cursor.fetchall()
conn.close()
print('Tables:', [t[0] for t in tables])
" 2>/dev/null; then
            log_pass "  ✓ 数据库可访问"
        else
            log_fail "  ✗ 数据库无法访问"
        fi
    else
        log_warn "数据库不存在: $db_path (部署时将初始化)"
    fi
}

# ============================================================
# 检查8: 系统资源
# ============================================================
check_resources() {
    log_info "检查系统资源..."
    
    # CPU
    if command -v nproc &>/dev/null; then
        local cpu_cores=$(nproc)
        log_pass "CPU 核心数: $cpu_cores"
        
        if [[ $cpu_cores -lt 2 ]]; then
            log_warn "CPU 核心数较少 (<2)，可能影响性能"
        fi
    fi
    
    # 内存
    if command -v free &>/dev/null; then
        local mem_total=$(free -g 2>/dev/null | awk 'NR==2 {print $2}')
        log_pass "内存总量: ${mem_total}GB"
        
        if [[ ${mem_total:-0} -lt 2 ]]; then
            log_warn "内存小于 2GB，可能影响性能"
        fi
    fi
}

# ============================================================
# 检查9: 网络连通性
# ============================================================
check_network() {
    log_info "检查网络连通性..."
    
    # 检查本地服务
    local frontend_port=$(get_config "services.frontend" "port" || echo "8081")
    local backend_port=$(get_config "services.backend" "port" || echo "5001")
    
    if curl -sf --max-time 2 "http://localhost:${frontend_port}/health" &>/dev/null; then
        log_pass "前端服务: 已运行 (端口 ${frontend_port})"
    else
        log_info "前端服务: 未运行 (正常状态)"
    fi
    
    if curl -sf --max-time 2 "http://localhost:${backend_port}/health" &>/dev/null; then
        log_pass "后端服务: 已运行 (端口 ${backend_port})"
    else
        log_info "后端服务: 未运行 (正常状态)"
    fi
}

# ============================================================
# 检查10: 部署包（可选）
# ============================================================
check_deploy_package() {
    local pkg_path="$1"
    
    if [[ -z "$pkg_path" ]]; then
        log_skip "部署包检查 (未提供路径)"
        return
    fi
    
    log_info "检查部署包..."
    
    if [[ ! -f "$pkg_path" ]]; then
        log_fail "部署包不存在: $pkg_path"
        return 1
    fi
    
    local size=$(du -h "$pkg_path" | cut -f1)
    log_pass "部署包: $pkg_path ($size)"
    
    # 验证 ZIP 完整性
    if command -v unzip &>/dev/null; then
        if unzip -t "$pkg_path" &>/dev/null; then
            log_pass "  ✓ 部署包完整"
        else
            log_fail "  ✗ 部署包损坏"
            return 1
        fi
        
        # 检查 MANIFEST
        if unzip -l "$pkg_path" 2>/dev/null | grep -q "MANIFEST"; then
            log_pass "  ✓ MANIFEST 存在"
        else
            log_warn "  ! MANIFEST 不存在"
        fi
    fi
}

# ============================================================
# 生成报告
# ============================================================
generate_report() {
    local report_path="${1:-/tmp/preflight-report.txt}"
    
    {
        echo "========================================"
        echo "       前置环境检查报告"
        echo "========================================"
        echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "服务器: $(hostname)"
        echo ""
        echo "检查结果汇总:"
        echo "  通过: $CHECKS_PASSED"
        echo "  失败: $CHECKS_FAILED"
        echo "  警告: $CHECKS_WARNING"
        echo "  跳过: $CHECKS_SKIPPED"
        echo ""
        
        if [[ ${CHECKS_FAILED} -gt 0 ]]; then
            echo "❌ 检查失败"
            echo ""
            echo "请先修复上述失败项后再进行部署"
        elif [[ ${CHECKS_WARNING} -gt 0 ]]; then
            echo "⚠️  检查有警告"
            echo ""
            echo "警告项不影响部署，但建议关注"
        else
            echo "✅ 检查全部通过"
        fi
        echo "========================================"
    } > "$report_path"
    
    echo ""
    cat "$report_path"
}

# ============================================================
# 主流程
# ============================================================
main() {
    echo "========================================"
    echo "       前置环境检查"
    echo "========================================"
    echo ""
    
    # 检查配置文件
    check_config_file || true
    
    # 执行各项检查
    check_os
    check_disk_space
    check_python
    check_directories
    check_ports
    check_database
    check_resources
    check_network
    
    # 如果提供了部署包参数，检查部署包
    if [[ $# -gt 0 ]]; then
        check_deploy_package "$1" || true
    fi
    
    # 生成报告
    generate_report "/tmp/preflight-report-$(date +%Y%m%d_%H%M%S).txt"
    
    # 最终结果
    echo ""
    echo "========================================"
    echo "       检查结果汇总"
    echo "========================================"
    echo -e "通过: ${GREEN}${CHECKS_PASSED}${NC}"
    echo -e "失败: ${RED}${CHECKS_FAILED}${NC}"
    echo -e "警告: ${YELLOW}${CHECKS_WARNING}${NC}"
    echo ""
    
    if [[ ${CHECKS_FAILED} -gt 0 ]]; then
        echo -e "${RED}❌ 环境检查失败，请先修复问题${NC}"
        exit 1
    elif [[ ${CHECKS_WARNING} -gt 0 ]]; then
        echo -e "${YELLOW}⚠️  环境有警告，建议检查${NC}"
        exit 0
    else
        echo -e "${GREEN}✅ 环境检查通过${NC}"
        exit 0
    fi
}

# 运行
main "$@"
