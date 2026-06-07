#!/usr/bin/env bash
# ============================================================
# 构建部署包脚本
# 在本地构建完整的部署包，包含所有依赖
# ============================================================

set -euo pipefail

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="${PROJECT_ROOT}/build"
VERSION="${1:-$(date +%Y%m%d)}_$(printf "%03d" ${2:-1})"
PACKAGE_NAME="deploy-v${VERSION}.zip"

log_info() { echo -e "${BLUE}[i]${NC} $*"; }
log_pass() { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn() { echo -e "${YELLOW}[!]${NC} $*"; }
log_fail() { echo -e "${RED}[✗]${NC} $*"; }

# ============================================================
# 清理旧构建
# ============================================================
cleanup() {
    log_info "清理旧构建..."
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
}

# ============================================================
# 构建前端
# ============================================================
build_frontend() {
    log_info "构建前端..."
    
    local frontend_src="${PROJECT_ROOT}/excel-to-diagram"
    local frontend_dist="$BUILD_DIR/frontend"
    
    if [[ ! -d "$frontend_src" ]]; then
        log_warn "前端源码目录不存在: $frontend_src，跳过构建"
        return
    fi
    
    cd "$frontend_src"
    
    # 检查 Node.js
    if ! command -v npm &>/dev/null; then
        log_warn "npm 未安装，无法构建前端"
        log_info "请手动构建前端: cd $frontend_src && npm install && npm run build"
        
        # 复制现有 dist 如果存在
        if [[ -d "$frontend_src/dist" ]]; then
            mkdir -p "$frontend_dist"
            cp -r "$frontend_src/dist/"* "$frontend_dist/" 2>/dev/null || true
            cp "$frontend_src/server.py" "$frontend_dist/" 2>/dev/null || true
            log_pass "复制现有构建文件"
        fi
        return
    fi
    
    # 安装依赖并构建
    npm install 2>/dev/null || true
    npm run build 2>/dev/null || {
        log_warn "前端构建失败，复制现有文件"
        if [[ -d "$frontend_src/dist" ]]; then
            mkdir -p "$frontend_dist"
            cp -r "$frontend_src/dist/"* "$frontend_dist/" 2>/dev/null || true
        fi
    }
    
    # 复制 server.py（带代理功能）
    if [[ -f "$frontend_src/server.py" ]]; then
        cp "$frontend_src/server.py" "$frontend_dist/"
    fi
    
    cd "$PROJECT_ROOT"
    log_pass "前端构建完成"
}

# ============================================================
# 复制后端
# ============================================================
copy_backend() {
    log_info "复制后端代码..."
    
    local backend_src="${PROJECT_ROOT}/meta"
    local backend_dist="$BUILD_DIR/backend"
    
    mkdir -p "$backend_dist"
    
    if [[ -d "$backend_src" ]]; then
        cp -r "$backend_src"/* "$backend_dist/"
        log_pass "后端代码已复制"
    else
        log_fail "后端源码目录不存在: $backend_src"
        exit 1
    fi
    
    # 复制 requirements.txt
    if [[ -f "${PROJECT_ROOT}/requirements.txt" ]]; then
        cp "${PROJECT_ROOT}/requirements.txt" "$backend_dist/"
    fi
    
    # 复制 server.py
    if [[ -f "${PROJECT_ROOT}/server.py" ]]; then
        cp "${PROJECT_ROOT}/server.py" "$backend_dist/"
    fi
}

# ============================================================
# 下载 Python 依赖（离线）
# ============================================================
download_python_deps() {
    log_info "准备 Python 依赖..."
    
    local deps_dir="$BUILD_DIR/dependencies/python/packages"
    mkdir -p "$deps_dir"
    
    # 检查 requirements.txt
    if [[ ! -f "${BUILD_DIR}/backend/requirements.txt" ]]; then
        log_warn "requirements.txt 不存在，跳过依赖下载"
        return
    fi
    
    # 检查 pip
    if ! command -v pip &>/dev/null; then
        log_warn "pip 未安装，跳过依赖下载"
        return
    fi
    
    # 下载依赖（wheel 格式）
    log_info "下载 Python 依赖包..."
    
    pip download \
        -r "${BUILD_DIR}/backend/requirements.txt" \
        -d "$deps_dir" \
        --platform manylinux2014_x86_64 \
        --python-version 39 \
        --only-binary=:all: \
        --no-deps \
        2>/dev/null || {
        log_warn "部分依赖下载失败，继续其他依赖..."
        pip download \
            -r "${BUILD_DIR}/backend/requirements.txt" \
            -d "$deps_dir" \
            --no-deps \
            2>/dev/null || true
    }
    
    local pkg_count=$(ls "$deps_dir" 2>/dev/null | wc -l)
    log_pass "已下载 $pkg_count 个 Python 包"
}

# ============================================================
# 创建迁移脚本目录
# ============================================================
copy_migrations() {
    log_info "复制迁移脚本..."
    
    local migrations_src="${PROJECT_ROOT}/migrations"
    local migrations_dist="$BUILD_DIR/migrations"
    
    mkdir -p "$migrations_dist"
    
    if [[ -d "$migrations_src" ]]; then
        cp -r "$migrations_src/"* "$migrations_dist/"
        log_pass "迁移脚本已复制"
    else
        log_warn "迁移脚本目录不存在: $migrations_src"
    fi
}

# ============================================================
# 复制脚本和配置
# ============================================================
copy_scripts_and_config() {
    log_info "复制脚本和配置..."
    
    # 复制部署脚本
    mkdir -p "$BUILD_DIR/scripts"
    if [[ -d "${PROJECT_ROOT}/scripts" ]]; then
        cp "${PROJECT_ROOT}/scripts/"*.sh "$BUILD_DIR/scripts/" 2>/dev/null || true
    fi
    
    # 复制配置文件
    mkdir -p "$BUILD_DIR/config"
    if [[ -d "${PROJECT_ROOT}/config" ]]; then
        cp -r "${PROJECT_ROOT}/config/"* "$BUILD_DIR/config/" 2>/dev/null || true
    fi
    
    log_pass "脚本和配置已复制"
}

# ============================================================
# 创建 MANIFEST
# ============================================================
create_manifest() {
    log_info "创建 MANIFEST..."
    
    local current_date=$(date -Iseconds)
    
    cat > "$BUILD_DIR/MANIFEST" << EOF
version: "v${VERSION}"
released_at: "${current_date}"
built_by: "build-deploy-package.sh"

changes:
  - "自动构建 $(date '+%Y-%m-%d %H:%M:%S')"

requirements:
  python: ">=3.8"
  disk_space: "500MB"

dependencies:
  python:
$(grep -v '^#' "${BUILD_DIR}/backend/requirements.txt" 2>/dev/null | grep -v '^$' | sed 's/^/    - /')

services:
  frontend:
    port: 8081
  backend:
    port: 5001
EOF
    
    log_pass "MANIFEST 已创建"
}

# ============================================================
# 打包
# ============================================================
create_package() {
    log_info "打包部署包..."
    
    cd "$BUILD_DIR"
    
    # 创建 zip 包
    zip -r "${PROJECT_ROOT}/${PACKAGE_NAME}" . -x "*.pyc" -x "__pycache__/*" -x "*.log"
    
    local size=$(du -h "${PROJECT_ROOT}/${PACKAGE_NAME}" | cut -f1)
    log_pass "部署包已创建: ${PACKAGE_NAME} ($size)"
}

# ============================================================
# 生成安装说明
# ============================================================
create_readme() {
    cat > "${PROJECT_ROOT}/DEPLOY-README-${VERSION}.txt" << EOF
================================================================================
                     Excel to Diagram 部署包
                     版本: v${VERSION}
                     日期: $(date '+%Y-%m-%d')
================================================================================

一、解压部署包
--------------
cd /opt/app
unzip ${PACKAGE_NAME}

二、前置检查
------------
/opt/app/scripts/preflight-check.sh

三、执行部署
------------
/opt/app/scripts/deploy.sh deploy-v${VERSION}.zip

四、验证部署
------------
# 健康检查
curl http://localhost:8081/health
curl http://localhost:5001/api/v1/health

# 功能测试
curl http://localhost:8081/api/v1/product?page_size=5

五、回滚（如有问题）
-------------------
/opt/app/scripts/rollback.sh

================================================================================
如有问题，请查看日志: /opt/app/shared/logs/
================================================================================
EOF
    
    log_pass "安装说明已创建: DEPLOY-README-${VERSION}.txt"
}

# ============================================================
# 主流程
# ============================================================
main() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}       构建部署包${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
    echo "版本: v${VERSION}"
    echo "项目目录: $PROJECT_ROOT"
    echo ""
    
    cleanup
    build_frontend
    copy_backend
    copy_migrations
    copy_scripts_and_config
    create_manifest
    
    # 如果有网络，下载依赖
    if ping -c 1 pypi.org &>/dev/null; then
        download_python_deps
    else
        log_warn "离线环境，跳过依赖下载"
    fi
    
    create_package
    create_readme
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}       构建完成${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "部署包: ${PROJECT_ROOT}/${PACKAGE_NAME}"
    echo "安装说明: ${PROJECT_ROOT}/DEPLOY-README-${VERSION}.txt"
    echo ""
}

main "$@"
