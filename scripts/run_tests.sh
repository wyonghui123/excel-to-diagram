#!/bin/bash
# 测试运行脚本 - Linux/Mac版本
# 用法: ./scripts/run_tests.sh [选项]
# 选项:
#   unit        - 仅运行单元测试
#   integration - 仅运行集成测试
#   api         - 仅运行API测试
#   performance - 仅运行性能测试
#   all         - 运行所有测试（默认）
#   coverage    - 运行测试并生成覆盖率报告

set -e

TEST_TYPE=${1:-all}

echo "========================================"
echo "测试类型: $TEST_TYPE"
echo "========================================"
echo

case "$TEST_TYPE" in
    unit)
        echo "运行单元测试..."
        pytest -m unit -v --tb=short
        ;;
    integration)
        echo "运行集成测试..."
        pytest -m integration -v --tb=short
        ;;
    api)
        echo "运行API测试..."
        pytest -m api -v --tb=short
        ;;
    performance)
        echo "运行性能测试..."
        pytest meta/tests/performance/ -v --tb=short
        echo
        echo "生成性能报告..."
        python -m meta.tests.performance.performance_reporter --format markdown
        ;;
    coverage)
        echo "运行所有测试并生成覆盖率报告..."
        pytest --cov=meta --cov-report=html --cov-report=term-missing -v --tb=short
        echo
        echo "覆盖率报告已生成: htmlcov/index.html"
        ;;
    all|*)
        echo "运行所有测试..."
        pytest -v --tb=short
        ;;
esac

echo
echo "========================================"
echo "测试完成"
echo "========================================"
