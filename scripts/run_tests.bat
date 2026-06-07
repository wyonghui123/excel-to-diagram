@echo off
REM 测试运行脚本 - Windows版本
REM 用法: scripts\run_tests.bat [选项]
REM 选项:
REM   unit        - 仅运行单元测试
REM   integration - 仅运行集成测试
REM   api         - 仅运行API测试
REM   performance - 仅运行性能测试
REM   all         - 运行所有测试（默认）
REM   coverage    - 运行测试并生成覆盖率报告

setlocal EnableDelayedExpansion

set TEST_TYPE=%1
if "%TEST_TYPE%"=="" set TEST_TYPE=all

echo ========================================
echo 测试类型: %TEST_TYPE%
echo ========================================
echo.

if "%TEST_TYPE%"=="unit" (
    echo 运行单元测试...
    pytest -m unit -v --tb=short
) else if "%TEST_TYPE%"=="integration" (
    echo 运行集成测试...
    pytest -m integration -v --tb=short
) else if "%TEST_TYPE%"=="api" (
    echo 运行API测试...
    pytest -m api -v --tb=short
) else if "%TEST_TYPE%"=="performance" (
    echo 运行性能测试...
    pytest meta/tests/performance/ -v --tb=short
    echo.
    echo 生成性能报告...
    python -m meta.tests.performance.performance_reporter --format markdown
) else if "%TEST_TYPE%"=="coverage" (
    echo 运行所有测试并生成覆盖率报告...
    pytest --cov=meta --cov-report=html --cov-report=term-missing -v --tb=short
    echo.
    echo 覆盖率报告已生成: htmlcov\index.html
) else (
    echo 运行所有测试...
    pytest -v --tb=short
)

echo.
echo ========================================
echo 测试完成
echo ========================================
