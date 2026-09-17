@echo off
REM testrunscript - Windowsversion
REM usage: scripts\run_tests.bat [option]
REM option:
REM   unit        - only-rununittest
REM   integration - only-runintegrationtest
REM   api         - only-runAPItest
REM   performance - only-runperftest
REM   all         - runalltest(default)
REM   coverage    - run-testsandgencoveragereport

setlocal EnableDelayedExpansion

set TEST_TYPE=%1
if "%TEST_TYPE%"=="" set TEST_TYPE=all

echo ========================================
echo testtype: %TEST_TYPE%
echo ========================================
echo.

if "%TEST_TYPE%"=="unit" (
    echo rununittest...
    pytest -m unit -v --tb=short
) else if "%TEST_TYPE%"=="integration" (
    echo runintegrationtest...
    pytest -m integration -v --tb=short
) else if "%TEST_TYPE%"=="api" (
    echo runAPItest...
    pytest -m api -v --tb=short
) else if "%TEST_TYPE%"=="performance" (
    echo runperftest...
    pytest meta/tests/performance/ -v --tb=short
    echo.
    echo genperfreport...
    python -m meta.tests.performance.performance_reporter --format markdown
) else if "%TEST_TYPE%"=="coverage" (
    echo runalltestandgencoveragereport...
    pytest --cov=meta --cov-report=html --cov-report=term-missing -v --tb=short
    echo.
    echo coveragereport-generated: htmlcov\index.html
) else (
    echo runalltest...
    pytest -v --tb=short
)

echo.
echo ========================================
echo testdone
echo ========================================
