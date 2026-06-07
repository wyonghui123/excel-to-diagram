#!/usr/bin/env bash
# ============================================================
# 部署后验证脚本
# 自动执行健康检查、生成快照、发送通知
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/app"
STATE_DIR="$APP_DIR/state"
LOG_DIR="$APP_DIR/shared/logs"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[✓]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
log_error() { echo -e "${RED}[✗]${NC} $1"; }
log_step() { echo -e "${BLUE}[→]${NC} $1"; }

# 显示帮助
show_help() {
    cat << EOF
用法: $(basename "$0") [选项]

部署后验证脚本 - 自动执行健康检查、生成快照、发送通知

选项:
    -h, --help          显示帮助信息
    -q, --quick         快速模式（跳过等待）
    -n, --no-snapshot   不生成快照
    -v, --verbose       详细输出

示例:
    $(basename "$0")                    # 完整验证流程
    $(basename "$0") -q                 # 快速验证
    $(basename "$0") -n                 # 不生成快照

EOF
}

# 等待服务启动
wait_for_services() {
    local max_wait=${1:-60}
    local interval=${2:-5}
    
    log_step "等待服务启动 (最多 ${max_wait} 秒)..."
    
    local elapsed=0
    while [[ $elapsed -lt $max_wait ]]; do
        local all_ready=true
        
        # 检查前端
        if ! curl -s -o /dev/null --max-time 2 http://localhost:8081/ 2>/dev/null; then
            all_ready=false
        fi
        
        # 检查后端
        if ! curl -s -o /dev/null --max-time 2 http://localhost:5001/api/v1/health 2>/dev/null; then
            all_ready=false
        fi
        
        # 检查 Admin
        if ! curl -s -o /dev/null --max-time 2 http://localhost:8080/admin 2>/dev/null; then
            all_ready=false
        fi
        
        if [[ "$all_ready" == "true" ]]; then
            log_info "所有服务已就绪"
            return 0
        fi
        
        sleep $interval
        elapsed=$((elapsed + interval))
        echo -n "."
    done
    
    echo ""
    log_warn "服务启动超时，继续执行验证..."
    return 1
}

# 执行健康检查
run_health_check() {
    log_step "执行健康检查..."
    
    if [[ -f "$SCRIPT_DIR/health-check.sh" ]]; then
        bash "$SCRIPT_DIR/health-check.sh" -q
        local result=$?
        
        if [[ $result -eq 0 ]]; then
            log_info "健康检查通过"
            return 0
        else
            log_warn "健康检查发现问题"
            return 1
        fi
    else
        log_warn "健康检查脚本不存在，跳过"
        return 0
    fi
}

# 生成快照
run_snapshot() {
    log_step "生成环境快照..."
    
    if [[ -f "$SCRIPT_DIR/snapshot-enhanced.sh" ]]; then
        bash "$SCRIPT_DIR/snapshot-enhanced.sh" snapshot
        log_info "快照已生成"
    else
        log_warn "快照脚本不存在，跳过"
    fi
}

# 生成部署报告
generate_report() {
    local health_status=$1
    local version=$(readlink "$APP_DIR/current" 2>/dev/null | xargs basename 2>/dev/null || echo "unknown")
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="$STATE_DIR/deploy-report-$(date +%Y%m%d-%H%M%S).txt"
    
    log_step "生成部署报告..."
    
    cat > "$report_file" << EOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  部署验证报告
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

部署时间: $timestamp
当前版本: $version
健康检查: $([[ $health_status -eq 0 ]] && echo "通过" || echo "有问题")

服务状态:
  前端 (8081): $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/ 2>/dev/null || echo "无法连接")
  后端 (5001): $(curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/api/v1/health 2>/dev/null || echo "无法连接")
  Admin (8080): $(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/admin 2>/dev/null || echo "无法连接")

访问地址:
  前端: http://$(hostname -I | awk '{print $1}'):8081
  后端: http://$(hostname -I | awk '{print $1}'):5001
  Admin: http://$(hostname -I | awk '{print $1}'):8080/admin

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
    
    log_info "报告已保存: $report_file"
    
    # 显示报告
    echo ""
    cat "$report_file"
    echo ""
}

# 主函数
main() {
    local quick_mode="false"
    local no_snapshot="false"
    local verbose="false"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -q|--quick)
                quick_mode="true"
                shift
                ;;
            -n|--no-snapshot)
                no_snapshot="true"
                shift
                ;;
            -v|--verbose)
                verbose="true"
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  部署后验证"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # 等待服务启动
    if [[ "$quick_mode" != "true" ]]; then
        wait_for_services 60 5
    fi
    
    # 执行健康检查
    run_health_check
    local health_result=$?
    
    # 生成快照
    if [[ "$no_snapshot" != "true" ]]; then
        run_snapshot
    fi
    
    # 生成报告
    generate_report $health_result
    
    # 最终结果
    echo ""
    if [[ $health_result -eq 0 ]]; then
        echo -e "${GREEN}✅ 部署验证完成，系统运行正常${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠️  部署验证完成，发现一些问题${NC}"
        exit 0
    fi
}

# 运行主函数
main "$@"
