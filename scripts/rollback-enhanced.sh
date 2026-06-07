#!/usr/bin/env bash
# ============================================================
# 增强版回滚脚本
# 支持自动备份、健康检查、快速回滚
# ============================================================

set -euo pipefail

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="/opt/app"
BACKUP_DIR="$APP_DIR/backups"
STATE_DIR="$APP_DIR/state"
LOG_DIR="$APP_DIR/shared/logs"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# 日志
log_info() { echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_DIR/rollback.log"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_DIR/rollback.log"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_DIR/rollback.log"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1" | tee -a "$LOG_DIR/rollback.log"; }
log_debug() { echo -e "${CYAN}[DEBUG]${NC} $1" | tee -a "$LOG_DIR/rollback.log"; }

# 确保日志目录存在
mkdir -p "$LOG_DIR"

# 显示帮助
show_help() {
    cat << EOF
用法: $(basename "$0") [选项] [版本号]

增强版回滚脚本 - 支持自动备份、健康检查、快速回滚

选项:
    -h, --help          显示帮助信息
    -l, --list          列出可用版本
    -b, --backup        回滚前创建当前版本备份
    -f, --force         强制回滚，跳过确认
    -c, --check-only    仅执行健康检查，不回滚
    -a, --auto          自动选择上一版本
    -s, --status        显示当前状态

示例:
    $(basename "$0")                    # 交互式选择版本回滚
    $(basename "$0") -l                 # 列出所有可用版本
    $(basename "$0") -b v20250415_001   # 备份后回滚到指定版本
    $(basename "$0") -a                 # 自动回滚到上一版本
    $(basename "$0") -c                 # 仅执行健康检查
    $(basename "$0") -s                 # 显示当前部署状态

EOF
}

# 获取当前版本
get_current_version() {
    if [[ -L "$APP_DIR/current" ]]; then
        readlink "$APP_DIR/current" | xargs basename
    else
        echo ""
    fi
}

# 列出可用版本
list_versions() {
    local current=$(get_current_version)
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  可用版本列表"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [[ ! -d "$APP_DIR/releases" ]]; then
        log_error "版本目录不存在: $APP_DIR/releases"
        return 1
    fi
    
    local count=0
    while IFS= read -r dir; do
        [[ -z "$dir" ]] && continue
        
        local ver=$(basename "$dir")
        local size=$(du -sh "$dir" 2>/dev/null | cut -f1)
        local mtime=$(stat -c %y "$dir" 2>/dev/null | cut -d' ' -f1)
        local marker=""
        
        if [[ "$ver" == "$current" ]]; then
            marker="${GREEN}<- 当前${NC}"
        fi
        
        printf "  %-20s %8s  %s  %s\n" "$ver" "$size" "$mtime" "$marker"
        ((count++))
    done < <(ls -1td "$APP_DIR/releases"/v* 2>/dev/null)
    
    if [[ $count -eq 0 ]]; then
        log_warn "没有找到任何版本"
        return 1
    fi
    
    echo ""
    echo "共 $count 个版本"
    echo ""
}

# 显示当前状态
show_status() {
    local current=$(get_current_version)
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  当前部署状态"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    if [[ -z "$current" ]]; then
        log_warn "当前没有激活的版本"
    else
        log_info "当前版本: $current"
    fi
    
    # 服务状态
    echo ""
    echo "服务状态:"
    
    # 前端服务 (8081)
    if netstat -tlnp 2>/dev/null | grep -q ":8081 "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":8081 " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        local proc=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        echo -e "  前端服务 (8081): ${GREEN}运行中${NC} (PID: $pid, $proc)"
    else
        echo -e "  前端服务 (8081): ${RED}未运行${NC}"
    fi
    
    # 后端服务 (5001)
    if netstat -tlnp 2>/dev/null | grep -q ":5001 "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":5001 " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        local proc=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        echo -e "  后端服务 (5001): ${GREEN}运行中${NC} (PID: $pid, $proc)"
    else
        echo -e "  后端服务 (5001): ${RED}未运行${NC}"
    fi
    
    # Admin 服务 (8080)
    if netstat -tlnp 2>/dev/null | grep -q ":8080 "; then
        local pid=$(netstat -tlnp 2>/dev/null | grep ":8080 " | head -1 | awk '{print $7}' | cut -d'/' -f1)
        local proc=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
        echo -e "  Admin服务 (8080): ${GREEN}运行中${NC} (PID: $pid, $proc)"
    else
        echo -e "  Admin服务 (8080): ${RED}未运行${NC}"
    fi
    
    # 磁盘空间
    echo ""
    echo "磁盘空间:"
    df -h / 2>/dev/null | awk 'NR==2 {printf "  总计: %s, 已用: %s, 可用: %s (使用率: %s)\n", $2, $3, $4, $5}'
    
    echo ""
}

# 创建备份
create_backup() {
    local current=$(get_current_version)
    
    if [[ -z "$current" ]]; then
        log_warn "当前没有激活的版本，跳过备份"
        return 0
    fi
    
    log_step "创建当前版本备份..."
    
    local backup_name="${current}_pre_rollback_$(date +%Y%m%d_%H%M%S)"
    local backup_path="$BACKUP_DIR/$backup_name"
    
    mkdir -p "$BACKUP_DIR"
    
    # 备份当前版本
    if [[ -d "$APP_DIR/releases/$current" ]]; then
        cp -r "$APP_DIR/releases/$current" "$backup_path"
        log_info "版本备份已创建: $backup_path"
    fi
    
    # 备份数据库
    local db_path="$APP_DIR/shared/data/architecture.db"
    if [[ -f "$db_path" ]]; then
        local db_backup="$BACKUP_DIR/${backup_name}_database.db"
        cp "$db_path" "$db_backup"
        log_info "数据库备份已创建: $db_backup"
    fi
    
    # 创建备份清单
    cat > "$backup_path/BACKUP_INFO.txt" << EOF
备份类型: 回滚前自动备份
原始版本: $current
备份时间: $(date '+%Y-%m-%d %H:%M:%S')
备份内容:
  - 应用版本
  - 数据库
EOF
    
    echo "$backup_name"
}

# 停止所有服务
stop_all_services() {
    log_step "停止所有服务..."
    
    # 停止前端 (8081)
    local frontend_pid=$(netstat -tlnp 2>/dev/null | grep ":8081 " | head -1 | awk '{print $7}' | cut -d'/' -f1)
    if [[ -n "$frontend_pid" ]]; then
        kill "$frontend_pid" 2>/dev/null || true
        log_info "前端服务已停止 (PID: $frontend_pid)"
    fi
    
    # 停止后端 (5001)
    local backend_pid=$(netstat -tlnp 2>/dev/null | grep ":5001 " | head -1 | awk '{print $7}' | cut -d'/' -f1)
    if [[ -n "$backend_pid" ]]; then
        kill "$backend_pid" 2>/dev/null || true
        log_info "后端服务已停止 (PID: $backend_pid)"
    fi
    
    # 停止 Admin (8080)
    local admin_pid=$(netstat -tlnp 2>/dev/null | grep ":8080 " | head -1 | awk '{print $7}' | cut -d'/' -f1)
    if [[ -n "$admin_pid" ]]; then
        kill "$admin_pid" 2>/dev/null || true
        log_info "Admin服务已停止 (PID: $admin_pid)"
    fi
    
    # 等待服务完全停止
    sleep 2
    
    # 强制清理残留进程
    for port in 8081 5001; do
        local pid=$(lsof -t -i:$port 2>/dev/null || true)
        if [[ -n "$pid" ]]; then
            kill -9 "$pid" 2>/dev/null || true
            log_warn "强制停止端口 $port 的进程 (PID: $pid)"
        fi
    done
    
    log_info "所有服务已停止"
}

# 健康检查
health_check() {
    local version=$1
    local max_attempts=${2:-30}
    local wait_seconds=${3:-2}
    
    log_step "执行健康检查 (版本: $version)..."
    
    local attempt=1
    while [[ $attempt -le $max_attempts ]]; do
        local all_healthy=true
        local errors=""
        
        # 检查前端服务
        local frontend_http=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8081/ 2>/dev/null || echo "000")
        if [[ "$frontend_http" != "200" ]]; then
            all_healthy=false
            errors="$errors 前端(8081)返回 $frontend_http;"
        fi
        
        # 检查后端服务
        local backend_http=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/api/v1/health 2>/dev/null || echo "000")
        if [[ "$backend_http" != "200" ]]; then
            all_healthy=false
            errors="$errors 后端(5001)返回 $backend_http;"
        fi
        
        # 检查 Admin 服务
        local admin_http=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/admin 2>/dev/null || echo "000")
        if [[ "$admin_http" != "200" && "$admin_http" != "302" ]]; then
            all_healthy=false
            errors="$errors Admin(8080)返回 $admin_http;"
        fi
        
        if [[ "$all_healthy" == "true" ]]; then
            log_info "健康检查通过！"
            return 0
        fi
        
        log_debug "检查 $attempt/$max_attempts: $errors"
        sleep $wait_seconds
        ((attempt++))
    done
    
    log_error "健康检查失败，服务未正常启动"
    return 1
}

# 执行回滚
perform_rollback() {
    local target_version=$1
    local do_backup=$2
    local force=$3
    
    local current=$(get_current_version)
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  回滚确认"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "  目标版本: $target_version"
    echo "  当前版本: ${current:-无}"
    echo "  创建备份: $([[ "$do_backup" == "true" ]] && echo "是" || echo "否")"
    echo ""
    
    if [[ "$force" != "true" ]]; then
        read -p "确认回滚? (y/n): " confirm
        [[ "$confirm" != "y" ]] && { log_info "取消回滚"; exit 0; }
    fi
    
    # 创建备份
    if [[ "$do_backup" == "true" && -n "$current" ]]; then
        create_backup
    fi
    
    # 停止服务
    stop_all_services
    
    # 切换版本
    log_step "切换到目标版本..."
    rm -f "$APP_DIR/current"
    ln -s "$APP_DIR/releases/$target_version" "$APP_DIR/current"
    log_info "已切换到: $target_version"
    
    # 启动服务
    log_step "启动服务..."
    
    # 启动后端
    if [[ -f "$APP_DIR/current/meta/server.py" ]]; then
        cd "$APP_DIR/current/meta"
        nohup python server.py > "$LOG_DIR/backend.log" 2>&1 &
        log_info "后端服务启动中..."
    fi
    
    # 启动前端
    if [[ -d "$APP_DIR/current/frontend" ]]; then
        cd "$APP_DIR/current/frontend"
        nohup python -m http.server 8081 > "$LOG_DIR/frontend.log" 2>&1 &
        log_info "前端服务启动中..."
    fi
    
    # 等待服务启动
    sleep 3
    
    # 健康检查
    if health_check "$target_version"; then
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        log_info "回滚成功！"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "  当前版本: $target_version"
        echo "  前端访问: http://$(hostname -I | awk '{print $1}'):8081"
        echo "  后端访问: http://$(hostname -I | awk '{print $1}'):5001"
        echo "  Admin访问: http://$(hostname -I | awk '{print $1}'):8080/admin"
        echo ""
        
        # 记录回滚历史
        cat >> "$STATE_DIR/rollback-history.log" << EOF
[$(date '+%Y-%m-%d %H:%M:%S')] 回滚成功
  从: ${current:-无}
  到: $target_version
  备份: $([[ "$do_backup" == "true" ]] && echo "是" || echo "否")
EOF
        
        return 0
    else
        log_error "回滚后健康检查失败"
        
        # 记录失败
        cat >> "$STATE_DIR/rollback-history.log" << EOF
[$(date '+%Y-%m-%d %H:%M:%S')] 回滚失败
  从: ${current:-无}
  到: $target_version
  错误: 健康检查失败
EOF
        
        return 1
    fi
}

# 主函数
main() {
    local target_version=""
    local do_backup="false"
    local force="false"
    local check_only="false"
    local auto_select="false"
    local show_status_flag="false"
    
    # 解析参数
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -l|--list)
                list_versions
                exit 0
                ;;
            -b|--backup)
                do_backup="true"
                shift
                ;;
            -f|--force)
                force="true"
                shift
                ;;
            -c|--check-only)
                check_only="true"
                shift
                ;;
            -a|--auto)
                auto_select="true"
                shift
                ;;
            -s|--status)
                show_status_flag="true"
                shift
                ;;
            -*)
                log_error "未知选项: $1"
                show_help
                exit 1
                ;;
            *)
                target_version="$1"
                shift
                ;;
        esac
    done
    
    # 显示状态
    if [[ "$show_status_flag" == "true" ]]; then
        show_status
        exit 0
    fi
    
    # 仅健康检查
    if [[ "$check_only" == "true" ]]; then
        local current=$(get_current_version)
        health_check "$current"
        exit $?
    fi
    
    # 自动选择上一版本
    if [[ "$auto_select" == "true" ]]; then
        local current=$(get_current_version)
        target_version=$(ls -1td "$APP_DIR/releases"/v* 2>/dev/null | grep -v "$current" | head -1 | xargs basename)
        
        if [[ -z "$target_version" ]]; then
            log_error "没有找到上一版本"
            exit 1
        fi
        
        log_info "自动选择上一版本: $target_version"
    fi
    
    # 交互式选择版本
    if [[ -z "$target_version" ]]; then
        list_versions
        
        local current=$(get_current_version)
        read -p "输入要回滚的版本号 (或按 Ctrl+C 取消): " target_version
        
        if [[ -z "$target_version" ]]; then
            log_error "未指定版本号"
            exit 1
        fi
    fi
    
    # 验证版本
    if [[ ! -d "$APP_DIR/releases/$target_version" ]]; then
        log_error "版本不存在: $target_version"
        exit 1
    fi
    
    local current=$(get_current_version)
    if [[ "$target_version" == "$current" ]]; then
        log_warn "已经是当前版本，无需回滚"
        exit 0
    fi
    
    # 执行回滚
    perform_rollback "$target_version" "$do_backup" "$force"
}

# 运行主函数
main "$@"
