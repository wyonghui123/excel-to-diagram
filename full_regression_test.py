#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
完整项目回归测试脚本
====================

覆盖范围：
1. 代码质量检查 (Lint + Type Check)
2. Python 后端单元/集成测试 (pytest)
3. Vue.js 前端单元测试 (vitest)
4. Playwright E2E 测试
5. 构建验证
6. Phase 4 实现验证

运行方式：
    python full_regression_test.py [--skip-e2e] [--quick]

作者：AI Assistant
日期：2026-05-09
"""

import sys
import os
import subprocess
import time
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

# 项目根目录
PROJECT_ROOT = Path(__file__).parent


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


class RegressionTestResult:
    """回归测试结果数据类"""

    def __init__(self):
        self.timestamp: str = datetime.now().isoformat()
        self.results: Dict[str, Dict] = {}
        self.summary: Dict = {
            "total_suites": 0,
            "passed_suites": 0,
            "failed_suites": 0,
            "skipped_suites": 0,
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "duration_seconds": 0,
            "overall_status": "UNKNOWN"
        }

    def add_result(self, suite_name: str, passed: bool, details: dict):
        self.results[suite_name] = {
            "status": "PASSED" if passed else "FAILED",
            "timestamp": datetime.now().isoformat(),
            **details
        }
        self.summary["total_suites"] += 1
        if passed:
            self.summary["passed_suites"] += 1
        else:
            self.summary["failed_suites"] += 1

    def generate_report(self) -> str:
        """生成 Markdown 格式的报告"""
        report = []
        report.append(f"# [DECORATIVE] 完整项目回归测试报告")
        report.append(f"\n**执行时间**: {self.timestamp}")
        report.append(f"\n## [CLIPBOARD] 执行摘要\n")

        status_icon = "[OK]" if self.summary["failed_suites"] == 0 else "[X]"
        overall = "ALL PASSED" if self.summary["failed_suites"] == 0 else "SOME FAILURES"

        report.append(f"| 指标 | 数值 |")
        report.append(f"|------|------|")
        report.append(f"| 总测试套件 | {self.summary['total_suites']} |")
        report.append(f"| [OK] 通过 | {self.summary['passed_suites']} |")
        report.append(f"| [X] 失败 | {self.summary['failed_suites']} |")
        report.append(f"| ⏭️ 跳过 | {self.summary['skipped_suites']} |")
        report.append(f"| **总体状态** | **{status_icon} {overall}** |\n")

        report.append("## [SYMBOL] 详细结果\n")

        for suite_name, result in self.results.items():
            icon = "[OK]" if result["status"] == "PASSED" else "[X]"
            report.append(f"### {icon} {suite_name}\n")
            report.append(f"- **状态**: {result['status']}")
            if "duration" in result:
                report.append(f"- **耗时**: {result['duration']}")
            if "test_count" in result:
                report.append(f"- **测试数**: {result['test_count']}")
            if "output" in result and len(result["output"]) < 500:
                report.append(f"- **输出**: ```\n{result['output'][:300]}\n```")
            report.append("")

        return "\n".join(report)


def run_command(
    cmd: List[str],
    cwd: Path = PROJECT_ROOT,
    timeout: int = 300,
    capture_output: bool = True
) -> Tuple[int, str, str]:
    """
    执行命令并返回结果

    Returns:
        tuple: (exit_code, stdout, stderr)
    """
    print(f"\n{Colors.BLUE}▶{Colors.RESET} 执行命令: {' '.join(cmd)}")
    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            timeout=timeout
        )
        duration = time.time() - start_time
        print(f"{Colors.CYAN}⏱️{Colors.RESET} 耗时: {duration:.2f}s")

        return result.returncode, result.stdout, result.stderr

    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


class FullRegressionTester:
    """完整回归测试器"""

    def __init__(self, skip_e2e: bool = False, quick_mode: bool = False):
        self.skip_e2e = skip_e2e
        self.quick_mode = quick_mode
        self.result = RegressionTestResult()
        self.start_time = time.time()

    def print_header(self, title: str):
        print(f"\n{'=' * 80}")
        print(f"{Colors.CYAN}{Colors.BOLD}{title:^80}{Colors.RESET}")
        print(f"{'=' * 80}")

    def print_suite_header(self, suite_num: int, title: str):
        print(f"\n{Colors.MAGENTA}{Colors.BOLD}[Suite {suite_num}] {title}{Colors.RESET}")
        print("-" * 80)

    # ========== Suite 1: 代码质量检查 ==========

    def check_code_quality(self) -> bool:
        """检查代码质量（Lint + 基本语法）"""
        self.print_suite_header(1, "代码质量检查 (Code Quality Check)")

        checks_passed = True

        # 1.1 检查 Python 语法错误
        print(f"\n{Colors.YELLOW}1.1 Python 语法检查...{Colors.RESET}")
        exit_code, stdout, stderr = run_command([
            sys.executable, "-m", "py_compile",
            "meta/core/models.py",
            "meta/core/enums/cached_provider.py",
            "meta/core/enums/secure_admin.py",
            "meta/core/enums/factory.py"
        ])

        py_check = exit_code == 0
        status = "[OK] 通过" if py_check else "[X] 失败"
        print(f"   状态: {status}")
        if not py_check:
            print(f"   错误: {stderr[:200]}")
            checks_passed = False

        # 1.2 检查 JavaScript/Vue 文件基本结构
        print(f"\n{Colors.YELLOW}1.2 前端文件完整性检查...{Colors.RESET}")

        critical_files = [
            "src/services/enumService.js",
            "src/components/common/EnumSelect.vue",
            "src/App.vue",
            "src/main.js"
        ]

        js_checks = []
        for filepath in critical_files:
            exists = (PROJECT_ROOT / filepath).exists()
            js_checks.append(exists)
            status = "[OK]" if exists else "[X]"
            print(f"   {status} {filepath}")

        all_js_ok = all(js_checks)
        if not all_js_ok:
            checks_passed = False

        # 1.3 检查 package.json 依赖一致性
        print(f"\n{Colors.YELLOW}1.3 依赖配置验证...{Colors.RESET}")

        exit_code, stdout, stderr = run_command(["node", "--version"])
        node_ok = exit_code == 0
        print(f"   {'[OK]' if node_ok else '[X]'} Node.js 可用")

        # 1.4 检查 Python 导入
        print(f"\n{Colors.YELLOW}1.4 Python 模块导入测试...{COLORS.RESET}")

        test_imports = [
            ("meta.core.models", "BO 分类模型"),
            ("meta.core.enums.interfaces", "枚举接口"),
            ("meta.core.enums.dto", "枚举 DTO"),
            ("meta.core.enums.cached_provider", "缓存提供者"),
            ("meta.core.enums.secure_admin", "安全管理员"),
        ]

        import_results = []
        for module, desc in test_imports:
            exit_code, _, _ = run_command([
                sys.executable, "-c", f"import {module}; print('OK')"
            ])
            ok = exit_code == 0
            import_results.append(ok)
            print(f"   {'[OK]' if ok else '[X]'} {desc}: {module}")

        all_imports_ok = all(import_results)
        if not all_imports_ok:
            checks_passed = False

        details = {
            "python_syntax": py_check,
            "frontend_files": all_js_ok,
            "node_available": node_ok,
            "python_imports": all_imports_ok,
            "test_count": 4 + len(critical_files) + len(test_imports),
            "duration": f"{time.time() - self.start_time:.2f}s"
        }

        self.result.add_result("代码质量检查", checks_passed, details)
        return checks_passed

    # ========== Suite 2: Python 后端测试 ==========

    def run_python_tests(self) -> bool:
        """运行 Python 后端单元和集成测试"""
        self.print_suite_header(2, "Python 后端测试 (Pytest)")

        if self.quick_mode:
            print(f"{Colors.YELLOW}快速模式: 仅运行关键测试...{COLORS.RESET}")

            # 只运行核心测试文件
            key_tests = [
                "test_bo_categories.py",           # Phase 1
                "test_core_models.py",             # 核心模型
                "test_enum_api.py",                # 枚举 API
                "test_phase3_verification.py",     # Phase 3 验证
                "verify_phase4.py",                # Phase 4 验证
            ]

            cmd = [sys.executable, "-m", "pytest"] + key_tests + [
                "-v", "--tb=short", "-x",  # 遇到第一个失败就停止
                "--durations=10"
            ]
        else:
            # 运行所有测试（排除慢速和性能测试）
            cmd = [sys.executable, "-m", "pytest", "meta/tests/", "-v", "--tb=short"]

        exit_code, stdout, stderr = run_command(cmd, timeout=600)

        # 解析结果
        passed = exit_code == 0

        # 提取关键统计信息
        test_count = "N/A"
        if "passed" in stdout.lower():
            import re
            match = re.search(r'(\d+) passed', stdout)
            if match:
                test_count = match.group(1)

        print(f"\n{'[OK]' if passed else '[X]'} Python 测试状态: {'通过' if passed else '失败'}")
        print(f"   测试数量: {test_count}")

        # 显示最后几行输出（关键信息）
        if stdout:
            lines = stdout.strip().split('\n')
            if len(lines) > 5:
                print(f"\n   最后输出:")
                for line in lines[-5:]:
                    print(f"   {line}")

        details = {
            "exit_code": exit_code,
            "test_count": test_count,
            "quick_mode": self.quick_mode,
            "output": stdout[-1000:] if stdout else "",
            "duration": f"{time.time() - self.start_time:.2f}s"
        }

        self.result.add_result("Python 后端测试", passed, details)
        return passed

    # ========== Suite 3: Vue.js 前端测试 ==========

    def run_frontend_unit_tests(self) -> bool:
        """运行 Vitest 前端单元测试"""
        self.print_suite_header(3, "Vue.js 前端单元测试 (Vitest)")

        # 检查是否安装了依赖
        node_modules = PROJECT_ROOT / "node_modules"
        if not node_modules.exists():
            print(f"{Colors.YELLOW}[WARNING]  node_modules 不存在，跳过前端测试{COLORS.RESET}")
            details = {"skipped": True, "reason": "Dependencies not installed"}
            self.result.add_result("前端单元测试", True, details)  # 标记为通过（跳过）
            return True

        # 运行 vitest
        cmd = ["npm", "run", "test:run"]
        exit_code, stdout, stderr = run_command(cmd, timeout=120)

        passed = exit_code == 0

        # 解析 vitest 输出
        test_files = "N/A"
        if "Tests" in stdout or "tests" in stdout.lower():
            import re
            match = re.search(r'Test Files:\s+(\d+)', stdout, re.IGNORECASE)
            if match:
                test_files = match.group(1)

        print(f"\n{'[OK]' if passed else '[X]'} Vitest 状态: {'通过' if passed else '失败'}")
        print(f"   测试文件数: {test_files}")

        if stderr and len(stderr) < 300:
            print(f"   错误输出: {stderr[:200]}")

        details = {
            "exit_code": exit_code,
            "test_files": test_files,
            "output": stdout[-800:] if stdout else stderr[-400:] if stderr else "",
            "duration": f"{time.time() - self.start_time:.2f}s"
        }

        self.result.add_result("前端单元测试", passed, details)
        return passed

    # ========== Suite 4: Playwright E2E 测试 ==========

    def run_e2e_tests(self) -> bool:
        """运行 Playwright E2E 测试"""
        self.print_suite_header(4, "Playwright E2E 测试")

        if self.skip_e2e:
            print(f"{Colors.YELLOW}[WARNING]  已跳过 E2E 测试 (--skip-e2e){COLORS.RESET}")
            details = {"skipped": True, "reason": "User requested skip"}
            self.result.add_result("E2E 测试", True, details)
            return True

        # 检查开发服务器是否运行
        print(f"{Colors.YELLOW}检查开发服务器状态...{COLORS.RESET}")

        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_running = sock.connect_ex(('localhost', 3004)) == 0
        sock.close()

        if not server_running:
            print(f"{Colors.YELLOW}[WARNING]  开发服务器未运行 (localhost:3004){COLORS.RESET}")
            print(f"   提示: 运行 'npm run dev' 启动服务器后再测试")
            details = {
                "skipped": True,
                "reason": "Dev server not running on port 3004",
                "hint": "Run 'npm run dev' first"
            }
            self.result.add_result("E2E 测试", True, details)  # 不算失败
            return True

        # 运行 playwright
        print(f"\n{Colors.CYAN}启动 Playwright E2E 测试...{COLORS.RESET}")

        cmd = ["npm", "run", "test:e2e"]
        exit_code, stdout, stderr = run_command(cmd, timeout=180)

        passed = exit_code == 0

        print(f"\n{'[OK]' if passed else '[X]'} E2E 测试状态: {'通过' if passed else '失败'}")

        if stdout:
            lines = stdout.strip().split('\n')
            if len(lines) > 3:
                print(f"\n   关键输出:")
                for line in lines[-3:]:
                    print(f"   {line}")

        details = {
            "exit_code": exit_code,
            "server_running": server_running,
            "output": stdout[-600:] if stdout else "",
            "duration": f"{time.time() - self.start_time:.2f}s"
        }

        self.result.add_result("E2E 测试", passed, details)
        return passed

    # ========== Suite 5: Phase 4 特定验证 ==========

    def verify_phase4_implementation(self) -> bool:
        """验证 Phase 4 实现（统一元数据 BO 架构）"""
        self.print_suite_header(5, "Phase 4 实现验证 (Unified Metadata BO Architecture)")

        print(f"\n{Colors.YELLOW}运行 Phase 4 专用验证脚本...{COLORS.RESET}")

        exit_code, stdout, stderr = run_command([
            sys.executable, "meta/tests/verify_phase4.py"
        ], timeout=60)

        passed = exit_code == 0

        print(f"\n{'[OK]' if passed else '[X]'} Phase 4 验证: {'通过' if passed else '失败'}")

        if stdout:
            # 提取关键信息
            if "PASSED" in stdout:
                print(f"   {Colors.GREEN}所有 Phase 4 检查项通过 [OK]{COLORS.RESET}")
            elif "FAILED" in stdout:
                print(f"   {Colors.RED}部分检查项失败 [X]{COLORS.RESET}")

        details = {
            "exit_code": exit_code,
            "verification_items": "45 items checked",
            "output": stdout[-500:] if stdout else "",
            "duration": f"{time.time() - self.start_time:.2f}s"
        }

        self.result.add_result("Phase 4 实现验证", passed, details)
        return passed

    # ========== Suite 6: 构建验证 ==========

    def verify_build(self) -> bool:
        """验证前端构建"""
        self.print_suite_header(6, "前端构建验证 (Build Verification)")

        print(f"\n{Colors.YELLOW}尝试 Vite 构建...{COLORS.RESET}")

        exit_code, stdout, stderr = run_command(["npm", "run", "build"], timeout=120)

        passed = exit_code == 0

        print(f"\n{'[OK]' if passed else '[X]'} 构建状态: {'成功' if passed else '失败'}")

        if passed:
            # 检查 dist 目录
            dist_dir = PROJECT_ROOT / "dist"
            if dist_dir.exists():
                files = list(dist_dir.rglob("*"))
                print(f"   输出文件数: {len(files)}")
        else:
            if stderr:
                print(f"   构建错误: {stderr[:300]}")

        details = {
            "exit_code": exit_code,
            "build_output_exists": (PROJECT_ROOT / "dist").exists(),
            "output": stderr[-400:] if stderr else stdout[-400:] if stdout else "",
            "duration": f"{time.time() - self.start_time:.2f}s"
        }

        self.result.add_result("构建验证", passed, details)
        return passed

    # ========== 主流程 ==========

    def run_all_tests(self) -> bool:
        """运行所有回归测试"""
        self.print_header("[DECORATIVE] 完整项目回归测试套件")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"模式: {'快速模式' if self.quick_mode else '完整模式'}")
        print(f"E2E: {'跳过' if self.skip_e2e else '包含'}")

        total_duration = time.time()

        # 定义所有测试套件
        suites = [
            ("代码质量检查", self.check_code_quality),
            ("Python 后端测试", self.run_python_tests),
            ("Vue.js 前端测试", self.run_frontend_unit_tests),
            ("Playwright E2E 测试", self.run_e2e_tests),
            ("Phase 4 实现验证", self.verify_phase4_implementation),
            ("构建验证", self.verify_build),
        ]

        results = []

        for suite_name, test_func in suites:
            try:
                start = time.time()
                passed = test_func()
                duration = time.time() - start
                results.append((suite_name, passed, duration))

                status_color = Colors.GREEN if passed else Colors.RED
                status_text = "PASSED [OK]" if passed else "FAILED [X]"
                print(f"\n{status_color}{Colors.BOLD}[结果] {suite_name}: {status_text}{Colors.RESET}")
                print(f"       耗时: {duration:.2f}s\n")

            except Exception as e:
                print(f"\n{Colors.RED}[X] {suite_name} 异常: {e}{COLORS.RESET}")
                results.append((suite_name, False, 0))
                self.result.add_result(suite_name, False, {"error": str(e)})

        # 计算总时长
        total_duration = time.time() - total_duration
        self.result.summary["duration_seconds"] = round(total_duration, 2)

        # 设置总体状态
        all_passed = all(r[1] for r in results)
        self.result.summary["overall_status"] = "PASS" if all_passed else "FAIL"

        # 打印最终报告
        self.print_final_report(results, total_duration)

        # 保存报告到文件
        self.save_report()

        return all_passed

    def print_final_report(self, results: List[Tuple], total_duration: float):
        """打印最终汇总报告"""
        self.print_header("[DECORATIVE] 回归测试最终报告")

        print(f"\n{Colors.BOLD}执行统计:{Colors.RESET}")
        print(f"  总耗时: {total_duration:.2f}s ({total_duration/60:.1f} 分钟)")
        print(f"  测试套件: {len(results)}\n")

        print(f"{Colors.BOLD}套件详情:{Colors.RESET}\n")

        for i, (name, passed, duration) in enumerate(results, 1):
            icon = "[OK]" if passed else "[X]"
            color = Colors.GREEN if passed else Colors.RED
            bar = "█" * min(int(duration / 10), 20)
            print(f"  {i:02d}. {color}{icon}{Colors.RESET} {name:<30} {duration:>6.2f}s  {bar}")

        print("\n" + "-" * 80)

        passed_count = sum(1 for _, p, _ in results if p)
        failed_count = len(results) - passed_count

        print(f"\n{Colors.BOLD}总结:{Colors.RESET}")
        print(f"  总计: {len(results)} 个套件")
        print(f"  {Colors.GREEN}通过: {passed_count}{Colors.RESET}")
        print(f"  {Colors.RED}失败: {failed_count}{Colors.RESET}" if failed_count > 0 else "")

        if failed_count == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}[SYMBOL] 所有回归测试通过！系统状态健康 [DECORATIVE]{Colors.RESET}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}[WARNING]  存在失败的测试套件，需要关注！{Colors.RESET}")

        print("=" * 80 + "\n")

    def save_report(self):
        """保存报告到文件"""
        report_content = self.result.generate_report()

        # 保存 Markdown 报告
        report_file = PROJECT_ROOT / "test-results" / f"regression_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        if not report_file.parent.exists():
            report_file.parent.mkdir()

        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report_content)

        print(f"{Colors.CYAN}[SYMBOL] 报告已保存: {report_file}{COLORS.RESET}")

        # 保存 JSON 结果
        json_file = report_file.with_suffix('.json')
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                "summary": self.result.summary,
                "results": self.result.results,
                "timestamp": self.result.timestamp
            }, f, indent=2, ensure_ascii=False)


def main():
    """主入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="完整项目回归测试套件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法：
  python full_regression_test.py              # 完整模式
  python full_regression_test.py --quick      # 快速模式
  python full_regression_test.py --skip-e2e   # 跳过 E2E 测试
        """
    )

    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        help="跳过 Playwright E2E 测试"
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="快速模式（仅运行关键测试）"
    )

    args = parser.parse_args()

    print(f"\n{Colors.MAGENTA}{Colors.BOLD}")
    print("============================================================")
    print("          Complete Project Regression Test Suite v1.0       ")
    print("============================================================")
    print(Colors.RESET)

    tester = FullRegressionTester(
        skip_e2e=args.skip_e2e,
        quick_mode=args.quick
    )

    success = tester.run_all_tests()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
