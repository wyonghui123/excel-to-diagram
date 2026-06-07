@echo off
REM 测试运行快捷方式 - 强制使用最佳实践

if "%1"=="" goto smart
if "%1"=="--all" goto all
if "%1"=="--failed" goto failed
if "%1"=="--status" goto status
if "%1"=="--watch" goto watch
goto usage

:smart
echo 智能运行测试...
python d:\filework\test.py
goto end

:all
echo 全量运行测试...
python d:\filework\test.py --all
goto end

:failed
echo 重跑失败测试...
python d:\filework\test.py --failed
goto end

:status
python d:\filework\test.py --status
goto end

:watch
python d:\filework\test.py --watch
goto end

:usage
echo.
echo 测试运行快捷方式
echo.
echo 用法: test.bat [选项]
echo.
echo 选项:
echo   (无参数)    智能运行（根据状态决定）
echo   --all       全量运行
echo   --failed    只跑失败的测试
echo   --status    查看状态
echo   --watch     持续监控
echo.

:end
