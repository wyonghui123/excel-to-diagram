#!/bin/bash
# scripts/run_all_tests.sh - v3.9 测试入口
# Usage: bash scripts/run_all_tests.sh
#   或: python tests/conftest.py
set -e

cd "$(dirname "$0")/.."
echo "============================================================"
echo "🧪 v3.9 BO Action 测试套件"
echo "============================================================"

# 检查服务
echo ""
echo "[1/8] 检查服务健康..."
curl -s --max-time 5 http://localhost:3010/api/v2/action/_health | head -c 200
echo ""

# 跑 conftest
echo ""
echo "[2/8] 跑 conftest (含 P0-1 SSE 真流式 + P0-2 并发 + P1-3 19 Action + P2-4 DB + P2-5 可观测性 + P3-6 SSE 长)..."
python tests/conftest.py

echo ""
echo "============================================================"
echo "✅ 测试完成"
echo "============================================================"
