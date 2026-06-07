#!/usr/bin/env bash
#
# 一键启动开发环境脚本
# 
# 功能：
# 1. 启动 Python Flask 后端
# 2. 启动 Vite 前端开发服务器
# 3. 自动同步端口配置
#
# 使用方法：
#   ./scripts/start-dev.sh
#
# Windows 使用：
#   bash scripts/start-dev.sh

set -e

# 获取脚本目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$ROOT_DIR"

echo "🔧 端口配置同步工具"
echo ""

# 运行端口同步脚本
node scripts/sync-ports.js

echo ""
echo "🚀 启动开发环境..."
echo ""

# 检查端口是否被占用
check_port() {
    local port=$1
    local name=$2
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1 || netstat -ano | grep -q ":$port.*LISTENING" 2>/dev/null; then
        echo "⚠️  端口 $port ($name) 已被占用，跳过启动"
        return 1
    fi
    return 0
}

# 启动 Python 后端（后台运行）
start_flask() {
    if check_port 5000 "Python Flask"; then
        echo "📦 启动 Python Flask 后端..."
        python -m meta.server &
        FLASK_PID=$!
        echo "   PID: $FLASK_PID"
    fi
}

# 启动 Vite 前端（后台运行）
start_vite() {
    if check_port 3004 "Vite Frontend"; then
        echo "📦 启动 Vite 前端开发服务器..."
        npm run dev &
        VITE_PID=$!
        echo "   PID: $VITE_PID"
    fi
}

# 主函数
main() {
    echo "═══════════════════════════════════════════════"
    echo "         开发环境启动脚本"
    echo "═══════════════════════════════════════════════"
    echo ""
    
    # 启动服务
    start_flask
    start_vite
    
    echo ""
    echo "═══════════════════════════════════════════════"
    echo "✅ 开发环境已启动！"
    echo ""
    echo "访问地址："
    echo "  前端:  http://localhost:3004"
    echo "  后端:  http://localhost:5000"
    echo ""
    echo "按 Ctrl+C 停止所有服务"
    echo "═══════════════════════════════════════════════"
    
    # 等待用户中断
    wait
}

main "$@"
