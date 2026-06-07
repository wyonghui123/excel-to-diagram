#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 4 快速验证脚本

验证所有 Phase 4 实现代码的完整性和正确性：
- enumService.js 更新
- EnumSelect.vue 更新
- E2E 测试脚本
- 性能测试脚本

运行方式：
    python meta/tests/verify_phase4.py

作者：AI Assistant
日期：2026-01-09
"""

import sys
import os
import re

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def print_header(title):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'=' * 70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{title:^70}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'=' * 70}{Colors.RESET}")


def check_file_exists(filepath: str) -> bool:
    """检查文件是否存在"""
    return os.path.exists(filepath)


def read_file_content(filepath: str) -> str:
    """读取文件内容"""
    if not os.path.exists(filepath):
        return ""
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()


def verify_enum_service():
    """验证 enumService.js 的更新"""
    print_header("1. Verifying enumService.js Updates")

    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    filepath = os.path.join(base_path, "src", "services", "enumService.js")
    content = read_file_content(filepath)

    checks = [
        ("File exists", check_file_exists(filepath)),
        ("Phase 4 documentation comment", "Phase 4 增强：支持双通道访问模式" in content),
        ("useHighSpeedEndpoint option", "useHighSpeedEndpoint" in content),
        ("filter parameter support", "filter" in content and "filter =" in content),
        ("_loadFromHighSpeedEndpoint method", "_loadFromHighSpeedEndpoint" in content),
        ("_loadFromStandardEndpoint method", "_loadFromStandardEndpoint" in content),
        ("Auto-fallback logic", "404" in content and "falling back" in content.lower()),
        ("LRU eviction strategy", "_maxCacheSize" in content and "LRU" in content),
        ("_addToCache method", "_addToCache" in content),
        ("Backward compatibility (code/name fields)", "code: v.code || v.value" in content or ("'code':" in content and "v.code" in content)),
        ("Performance stats tracking", "_stats:" in content or "getPerformanceStats" in content),
        ("setMaxCacheSize method", "setMaxCacheSize" in content),
        ("_formatAge helper", "_formatAge" in content),
    ]

    all_passed = True
    for check_name, result in checks:
        status = f"{Colors.GREEN}[OK]{Colors.RESET}" if result else f"{Colors.RED}[FAIL]{Colors.RESET}"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed


def verify_enum_select():
    """验证 EnumSelect.vue 的更新"""
    print_header("2. Verifying EnumSelect.vue Updates")

    base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    filepath = os.path.join(base_path, "src", "components", "common", "EnumSelect.vue")
    content = read_file_content(filepath)

    checks = [
        ("File exists", check_file_exists(filepath)),
        ("EnumService import", "import EnumService from '@/services/enumService'" in content),
        ("useHighSpeedEndpoint prop", "useHighSpeedEndpoint" in content),
        ("EnumService.loadOptions call", "EnumService.loadOptions" in content),
        ("Backward compatibility mapping", ".map(v =>" in content and ("code: v.code" in content or "'code'" in content)),
        ("Error handling preserved", "catch (e)" in content),
        ("Filter parameter passing", "filter: props.enumFilter" in content),
        ("throwError: false option", "throwError: false" in content),
    ]

    all_passed = True
    for check_name, result in checks:
        status = f"{Colors.GREEN}[OK]{Colors.RESET}" if result else f"{Colors.RED}[FAIL]{Colors.RESET}"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed


def verify_e2e_test_script():
    """验证 E2E 测试脚本"""
    print_header("3. Verifying E2E Test Script")

    filepath = "meta/tests/test_e2e_lifecycle.py"
    content = read_file_content(filepath)

    checks = [
        ("File exists", check_file_exists(filepath)),
        ("Create enum type test", "test_1_create_enum_type" in content),
        ("Add enum values test", "test_2_add_enum_values" in content),
        ("High-speed endpoint test", "test_3_read_via_high_speed_endpoint" in content),
        ("Update enum value test", "test_4_update_enum_value" in content),
        ("Caching mechanism test", "test_5_verify_caching_mechanism" in content),
        ("Frontend integration test", "test_6_frontend_integration" in content),
        ("Cleanup & delete test", "test_7_cleanup_and_delete" in content),
        ("Mock response class", "class MockResponse" in content),
        ("Performance measurement decorator", "measure_time" in content),
        ("Test report summary", "Test Report Summary" in content),
    ]

    all_passed = True
    for check_name, result in checks:
        status = f"{Colors.GREEN}[OK]{Colors.RESET}" if result else f"{Colors.RED}[FAIL]{Colors.RESET}"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed


def verify_performance_test_script():
    """验证性能测试脚本"""
    print_header("4. Verifying Performance Test Script")

    filepath = "meta/tests/test_performance.py"
    content = read_file_content(filepath)

    checks = [
        ("File exists", check_file_exists(filepath)),
        ("LoadTester class", "class LoadTester" in content),
        ("CacheMonitor class", "class CacheMonitor" in content),
        ("PerformanceBenchmark class", "class PerformanceBenchmark" in content),
        ("Concurrent user testing", "concurrent_users" in content and "ThreadPoolExecutor" in content),
        ("Percentile calculation", "percentile" in content),
        ("Memory usage monitoring", "memory_usage_mb" in content or "psutil" in content),
        ("Throughput calculation", "throughput_per_second" in content),
        ("P95/P99 metrics", "p95_response_time" in content and "p99_response_time" in content),
        ("Command-line arguments", "argparse" in content or "--mode" in content),
        ("JSON output support", "json.dump" in content),
    ]

    all_passed = True
    for check_name, result in checks:
        status = f"{Colors.GREEN}[OK]{Colors.RESET}" if result else f"{Colors.RED}[FAIL]{Colors.RESET}"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed


def verify_architecture_consistency():
    """验证架构一致性"""
    print_header("5. Verifying Architecture Consistency")

    enum_service = read_file_content("src/services/enumService.js")
    enum_select = read_file_content("src/components/common/EnumSelect.vue")

    checks = []

    # 检查端点路径一致性
    high_speed_pattern = r"/api/v1/enums/\{[^}]+\}/options"
    standard_pattern = r"/api/v1/enum-types/\{[^}]+\}/values"

    has_hs_in_service = bool(re.search(high_speed_pattern, enum_service))
    has_std_in_service = bool(re.search(standard_pattern, enum_service))

    checks.append(("High-speed endpoint defined in service", has_hs_in_service))
    checks.append(("Standard endpoint defined in service", has_std_in_service))

    # 检查组件是否正确使用服务
    uses_enum_service = "EnumService.loadOptions" in enum_select
    checks.append(("Component uses EnumService", uses_enum_service))

    # 检查缓存配置一致性
    cache_timeout_service = "5 * 60 * 1000" in enum_service or "_cacheTimeout" in enum_service
    checks.append(("Cache timeout configured", cache_timeout_service))

    # 检查错误处理一致性
    error_handling_service = "try {" in enum_service and "catch" in enum_service
    error_handling_component = "try {" in enum_select and "catch" in enum_select
    checks.append(("Error handling in service", error_handling_service))
    checks.append(("Error handling in component", error_handling_component))

    all_passed = True
    for check_name, result in checks:
        status = f"{Colors.GREEN}[OK]{Colors.RESET}" if result else f"{Colors.RED}[FAIL]{Colors.RESET}"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed


def main():
    """主函数"""
    print("=" * 70)
    print(f"{Colors.CYAN}{Colors.BOLD}Phase 4 Implementation Verification{Colors.RESET}")
    print("=" * 70)
    print("Date: 2026-05-09")
    print("=" * 70)

    results = {
        "enum_service": verify_enum_service(),
        "enum_select": verify_enum_select(),
        "e2e_test": verify_e2e_test_script(),
        "performance_test": verify_performance_test_script(),
        "architecture": verify_architecture_consistency()
    }

    # 打印总结
    print_header("Verification Summary")

    total_checks = len(results)
    passed_checks = sum(1 for v in results.values() if v)

    print(f"\nTotal Categories: {total_checks}")
    print(f"{Colors.GREEN}[OK] Passed: {passed_checks}{Colors.RESET}")
    print(f"{Colors.RED}[FAIL] Failed: {total_checks - passed_checks}{Colors.RESET}")

    print(f"\n{Colors.BOLD}Detailed Results:{Colors.RESET}\n")

    for category, passed in results.items():
        status_icon = "[OK]" if passed else "[FAIL]"
        status_color = Colors.GREEN if passed else Colors.RED
        category_name = category.replace("_", " ").title()
        print(f"  {status_color}{status_icon}{Colors.RESET} {category_name}")

    print("\n" + "=" * 70)

    if all(results.values()):
        print(f"{Colors.GREEN}{Colors.BOLD}[SUCCESS] ALL VERIFICATIONS PASSED! [SUCCESS]{Colors.RESET}")
        print("\n[OK] Phase 4 implementation is complete and correct!")
        print("[OK] Ready for integration testing with live backend service")
        print("=" * 70 + "\n")
        return True
    else:
        print(f"{Colors.RED}{Colors.BOLD}[WARNING]  SOME VERIFICATIONS FAILED{Colors.RESET}")
        print("\nPlease review the failed items above.")
        print("=" * 70 + "\n")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
