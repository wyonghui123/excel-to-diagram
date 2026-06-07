#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
E2E v2 规范检查器

检查 .spec.js 是否违反 v2 简化方案规范。
任何 Agent 写完 features 测试后必须运行本脚本。

用法：
  python e2e/scripts/check_v2_compliance.py [path]

示例：
  python e2e/scripts/check_v2_compliance.py
  python e2e/scripts/check_v2_compliance.py e2e/features/my-test.spec.js
"""
import re
import sys
from pathlib import Path
from typing import List, Tuple

# v2 规范：禁止的写法
FORBIDDEN_PATTERNS = [
    # (pattern, violation_name, severity, suggestion)
    (
        r"from\s+['\"]@playwright/test['\"]",
        "直接 import @playwright/test",
        "ERROR",
        "应改为: from '../helpers/auto-fixtures.js'"
    ),
    (
        r"await\s+login\s*\(",
        "测试内调用 login()",
        "ERROR",
        "应删除（global-setup.js 已处理认证）"
    ),
    (
        r"await\s+setAdminPermissions\s*\(",
        "测试内调用 setAdminPermissions()",
        "ERROR",
        "应删除（global-setup.js 已处理）"
    ),
    (
        r"await\s+page\.goto\s*\(",
        "直接 page.goto()",
        "WARNING",
        "建议改用: await navigateTo(page, path, opts)"
    ),
    (
        r"page\.locator\s*\(\s*['\"]\.el-table",
        "直接 page.locator('.el-table...')",
        "ERROR",
        "应改用 POM: new ArchDataPage(page).method(...)"
    ),
    (
        r"await\s+page\.waitForTimeout\s*\(\s*\d+\s*\)",
        "硬编码 waitForTimeout()",
        "WARNING",
        "建议改用: await waitForApiFn(page, 'METHOD URL')"
    ),
    (
        r"await\s+test\.step\s*\(",
        "使用 test.step()",
        "WARNING",
        "建议改用: await withStep(page, testInfo, 'name', fn)"
    ),
    (
        r"\$\{Date\.now\(\)\}",
        "硬编码 Date.now() 命名",
        "ERROR",
        "应改用: isolation.createTracked('type', { code: 'E2E_xxx', ... })"
    ),
    (
        r"await\s+getAuthHeaders\s*\(",
        "手动 getAuthHeaders()",
        "WARNING",
        "建议改用: isolation.createTracked() 内部已处理认证"
    ),
]

# v2 规范：鼓励的写法
RECOMMENDED_IMPORTS = [
    r"from\s+['\"]\.\.?/helpers/auto-fixtures\.js['\"]",
    r"from\s+['\"]\.\.?/helpers/auto-trace\.js['\"]",
    r"from\s+['\"]\.\.?/page-objects/",
]

# v2 规范：必须解构的 fixtures
REQUIRED_FIXTURES = [
    "isolation",  # 测试隔离 + 自动清理
]


def check_file(filepath: Path) -> Tuple[int, List[str]]:
    """检查单个 .spec.js 文件，返回 (错误数, 警告列表)"""
    if not filepath.exists():
        return 0, [f"[X] 文件不存在: {filepath}"]

    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')

    errors = 0
    warnings = []

    # 跳过 smoke 测试（允许保留 v1 写法）
    if '.smoke.spec.js' in filepath.name:
        return 0, ["ℹ️  smoke 测试，跳过 v2 检查"]

    # 跳过 demo 测试
    if '/demo/' in str(filepath):
        return 0, ["ℹ️  demo 测试，跳过 v2 检查"]

    # 检查禁止的写法
    for pattern, name, severity, suggestion in FORBIDDEN_PATTERNS:
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                msg = f"  [{severity}] 第 {i} 行: {name}\n    代码: {line.strip()}\n    建议: {suggestion}"
                if severity == "ERROR":
                    errors += 1
                    warnings.append(f"[X] {msg}")
                else:
                    warnings.append(f"[WARNING]  {msg}")

    # 检查是否是 test() 定义（不是 helper 文件）
    has_test = re.search(r"\btest\.(?:only|skip)?\s*\(", content) or re.search(r"\btest\.describe\s*\(", content)
    if not has_test:
        return 0, ["ℹ️  非测试文件，跳过 v2 检查"]

    # 检查是否使用 v2 import
    uses_v2_import = any(re.search(p, content) for p in RECOMMENDED_IMPORTS)
    if not uses_v2_import and 'auto-fixtures' not in content:
        warnings.append("[WARNING]  未发现 v2 推荐 import（auto-fixtures.js / auto-trace.js / page-objects/）")

    # 检查 fixture 解构（仅在有 test() 时）
    for fixture in REQUIRED_FIXTURES:
        # 简单检查：test 函数参数里是否有解构这个 fixture
        if f"isolation" not in content:
            warnings.append(f"[WARNING]  未解构 fixture: {fixture}（测试结束后无法自动清理数据）")

    return errors, warnings


def main():
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_file():
            files = [target]
        else:
            files = list(target.glob("**/*.spec.js"))
    else:
        # 默认检查 e2e/features
        project_root = Path(__file__).parent.parent.parent
        files = list((project_root / "e2e" / "features").glob("*.spec.js"))

    if not files:
        print("[X] 未找到 .spec.js 文件")
        return 1

    print(f"[SEARCH] 检查 {len(files)} 个测试文件是否符合 v2 简化方案规范\n")

    total_errors = 0
    files_with_issues = 0

    for filepath in sorted(files):
        errors, warnings = check_file(filepath)
        if errors > 0 or warnings:
            files_with_issues += 1
            print(f"[SYMBOL] {filepath.relative_to(Path.cwd()) if Path.cwd() in filepath.parents else filepath}")
            for w in warnings:
                print(w)
            print()
        total_errors += errors

    # 总结
    print("=" * 60)
    if total_errors == 0:
        print(f"[OK] 全部 {len(files)} 个文件通过 v2 规范检查（{files_with_issues} 个有警告）")
        return 0
    else:
        print(f"[X] {files_with_issues}/{len(files)} 个文件违反 v2 规范，{total_errors} 个错误")
        print()
        print("[DECORATIVE] 详细规范: .trae/rules/e2e-simplification.md")
        print("[DECORATIVE] v2 实施报告: e2e/TEST_SIMPLIFICATION_REPORT.md")
        return 1


if __name__ == "__main__":
    sys.exit(main())
