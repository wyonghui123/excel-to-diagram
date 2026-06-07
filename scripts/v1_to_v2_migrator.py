# -*- coding: utf-8 -*-
"""
v1 → v2 Spec 迁移工具

v1 模式 → v2 等价:
1. import { test, expect } from '@playwright/test'  →  import { test, expect } from '../helpers/auto-fixtures.js'
2. import { login, setAdminPermissions, ... } from '../helpers/auth.js'  →  (删除, 用 fixture)
3. await login(page) + await setAdminPermissions(page)  →  (删除, 用 devLogin fixture)
4. await navigateAndWaitForPage(page, url, opts)  →  await navigateTo(page, url)
5. await page.goto(url)  →  await navigateTo(page, url) (如果是在 navigateTo 之后)
6. await page.waitForTimeout(N)  →  await waitForApiFn(page, 'GET /api/...') 或 withStep
7. attachAndVerifyScreenshot(page, testInfo, name)  →  withStep(page, testInfo, name, fn)
8. page.locator('.el-table')  →  (用 POM: archData.getRowCount())
9. page.locator('input[placeholder*="搜索"]')  →  archData.search(text)
10. page.locator('.el-tabs__item:has-text("...")')  →  archData.openTab(name)

输出:
- reports/v1_to_v2_plan.md (52 specs 计划)
- reports/v1_to_v2_plan.json (结构化)
- 每 spec 的迁移状态: safe / semi-safe / complex
"""
import json
import re
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Tuple


# v1 模式 → (替换类型, 描述, 是否安全 auto-fix)
V1_PATTERNS = [
    # import
    {
        'name': 'pw_import',
        'pattern': r"import\s*\{\s*test\s*,\s*expect\s*\}\s*from\s*['\"]@playwright/test['\"]",
        'replacement': "import { test, expect } from '../helpers/auto-fixtures.js'",
        'safe': True,
        'category': 'import',
    },
    # v1 helpers imports - 标记为需删除
    {
        'name': 'auth_import',
        'pattern': r"import\s*\{([^}]+)\}\s*from\s*['\"]\.\./helpers/auth(?:\.js)?['\"]",
        'type': 'check_only',
        'extract': True,
        'safe': True,
        'category': 'import',
    },
    # login + setAdminPermissions
    {
        'name': 'login_call',
        'pattern': r"^\s*await\s+login\(page\)\s*;?\s*$",
        'multi': True,
        'safe': True,
        'category': 'auth',
    },
    {
        'name': 'setAdminPermissions_call',
        'pattern': r"^\s*await\s+setAdminPermissions\(page\)\s*;?\s*$",
        'multi': True,
        'safe': True,
        'category': 'auth',
    },
    # navigateAndWaitForPage
    {
        'name': 'navigateAndWaitForPage',
        'pattern': r"await\s+navigateAndWaitForPage\s*\(\s*page\s*,\s*['\"]([^'\"]+)['\"]([^)]*)\)",
        'type': 'navigate',
        'extract_url': 1,
        'extract_opts': 2,
        'safe': True,
        'category': 'navigation',
    },
    # page.goto
    {
        'name': 'page_goto',
        'pattern': r"await\s+page\.goto\s*\(\s*['\"]([^'\"]+)['\"]",
        'extract_url': 1,
        'safe': True,
        'category': 'navigation',
    },
    # waitForTimeout
    {
        'name': 'waitForTimeout',
        'pattern': r"await\s+page\.waitForTimeout\s*\(\s*(\d+)\s*\)",
        'extract_ms': 1,
        'safe': False,  # 替换为 waitForApiFn 需要 API 信息
        'category': 'wait',
    },
    # attachScreenshot
    {
        'name': 'attachScreenshot',
        'pattern': r"await\s+attach(?:AndVerify)?Screenshot\s*\(\s*page\s*,\s*testInfo\s*,\s*['\"]([^'\"]+)['\"]([^)]*)\)",
        'extract_name': 1,
        'safe': False,  # 需要重构为 withStep 包裹
        'category': 'screenshot',
    },
    # 直接 el-table locator
    {
        'name': 'el_table_locator',
        'pattern': r"page\.locator\s*\(\s*['\"]\.el-table",
        'safe': False,
        'category': 'pom',
    },
    # 直接 .el-tabs__item
    {
        'name': 'el_tabs_item',
        'pattern': r"page\.locator\s*\(\s*['\"]\.el-tabs__item",
        'safe': False,
        'category': 'pom',
    },
    # 搜索输入
    {
        'name': 'search_input',
        'pattern': r"page\.locator\s*\(\s*['\"]input\[placeholder\*?=['\"][^'\"]*搜索[^'\"]*['\"]",
        'safe': False,
        'category': 'pom',
    },
]


def analyze_spec(spec_path: Path) -> Dict:
    """分析单个 v1 spec,返回迁移状态"""
    content = spec_path.read_text(encoding='utf-8')
    matches = defaultdict(int)
    samples = defaultdict(list)
    details = []

    for pat_def in V1_PATTERNS:
        pat = pat_def['pattern']
        regex = re.compile(pat, re.MULTILINE)
        found = regex.findall(content)
        if found:
            name = pat_def['name']
            matches[name] = len(found)
            # 收集 sample (前 3 个)
            for f in found[:3]:
                if isinstance(f, tuple):
                    samples[name].append(f)
                else:
                    samples[name].append(f)
            details.append({
                'pattern': name,
                'count': len(found),
                'safe': pat_def['safe'],
                'category': pat_def['category'],
            })

    # 评估复杂度
    total_changes = sum(matches.values())
    safe_changes = sum(d['count'] for d in details if d['safe'])
    unsafe_changes = sum(d['count'] for d in details if not d['safe'])

    # 复杂度分类
    if unsafe_changes == 0 and total_changes <= 2:
        complexity = 'simple'  # 仅 import + login
    elif unsafe_changes <= 2:
        complexity = 'moderate'  # 1-2 个 POM/withStep 重构
    elif unsafe_changes <= 5:
        complexity = 'complex'
    else:
        complexity = 'very_complex'

    return {
        'spec': spec_path.name,
        'total_changes': total_changes,
        'safe_changes': safe_changes,
        'unsafe_changes': unsafe_changes,
        'complexity': complexity,
        'details': details,
        'samples': dict(samples),
        'line_count': len(content.splitlines()),
        'test_count': len(re.findall(r"^\s*test\s*\(\s*['\"]", content, re.MULTILINE)),
    }


def estimate_effort(complexity: str) -> str:
    """估算迁移工作量"""
    return {
        'simple': '5-10 min (auto-fix + 验证)',
        'moderate': '15-30 min (1-2 POM 重构)',
        'complex': '0.5-1 hour (3-5 处重构)',
        'very_complex': '1-2 hours (深度重构)',
    }.get(complexity, '? min')


def main():
    # 无参数也允许,使用默认输出

    output_md = 'reports/v1_to_v2_plan.md'
    output_json = 'reports/v1_to_v2_plan.json'
    migrate_target = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == '--output' and i + 1 < len(args):
            output_md = args[i + 1]
            i += 2
        elif args[i] == '--json' and i + 1 < len(args):
            output_json = args[i + 1]
            i += 2
        elif args[i] == '--migrate' and i + 1 < len(args):
            migrate_target = args[i + 1]
            i += 2
        else:
            i += 1

    # 扫描所有 v1 spec
    specs_dir = Path(r'e2e/features')
    v1_specs = []
    for f in specs_dir.glob('*.spec.js'):
        c = f.read_text(encoding='utf-8', errors='ignore')
        # 已经是 v2 风格 (有 auto-fixtures.js) 的跳过
        if 'auto-fixtures.js' in c:
            continue
        v1_specs.append(f)

    print(f"[1] 扫描到 {len(v1_specs)} 个 v1 spec")

    # 分析
    analyses = []
    for spec in sorted(v1_specs):
        try:
            result = analyze_spec(spec)
            analyses.append(result)
        except Exception as e:
            print(f"  [WARN] {spec.name} 分析失败: {e}")

    # 统计
    complexity_count = defaultdict(int)
    total_safe = 0
    total_unsafe = 0
    for a in analyses:
        complexity_count[a['complexity']] += 1
        total_safe += a['safe_changes']
        total_unsafe += a['unsafe_changes']

    # 排序:unsafe 多优先(最难)
    analyses.sort(key=lambda x: (-x['unsafe_changes'], -x['total_changes']))

    # 生成报告
    md_lines = []
    md_lines.append('# v1 → v2 Spec 迁移计划')
    md_lines.append('')
    md_lines.append(f'> **生成时间**: {Path(__file__).stat().st_mtime}')
    md_lines.append(f'> **生成工具**: scripts/v1_to_v2_migrator.py')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('## 一、概览')
    md_lines.append('')
    md_lines.append('| 指标 | 数值 |')
    md_lines.append('|------|------|')
    md_lines.append(f'| **v1 spec 总数** | **{len(v1_specs)}** |')
    md_lines.append(f'| **总计需修改处** | **{total_safe + total_unsafe}** |')
    md_lines.append(f'| 自动安全修改 | {total_safe} |')
    md_lines.append(f'| 需手动重构 | {total_unsafe} |')
    md_lines.append('')
    md_lines.append('### 复杂度分布')
    md_lines.append('')
    md_lines.append('| 复杂度 | 数量 | 占比 | 单个估时 |')
    md_lines.append('|--------|------|------|---------|')
    for c in ['simple', 'moderate', 'complex', 'very_complex']:
        n = complexity_count[c]
        pct = n / len(v1_specs) * 100 if v1_specs else 0
        eff = estimate_effort(c)
        md_lines.append(f'| {c} | {n} | {pct:.1f}% | {eff} |')
    md_lines.append('')

    # 总估时
    total_minutes = (
        complexity_count['simple'] * 7 +
        complexity_count['moderate'] * 22 +
        complexity_count['complex'] * 45 +
        complexity_count['very_complex'] * 90
    )
    md_lines.append(f'**总估时**: ~{total_minutes // 60}h {total_minutes % 60}min ({len(v1_specs)} specs)')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('## 二、推荐迁移顺序 (按 ROI)')
    md_lines.append('')
    md_lines.append('优先级规则:')
    md_lines.append('- **P0 (本周)**: simple + moderate (易改) - 立即出价值')
    md_lines.append('- **P1 (下周)**: complex (中等难度)')
    md_lines.append('- **P2 (本月)**: very_complex (高难度)')
    md_lines.append('')
    md_lines.append('| 优先级 | 数量 | 总估时 |')
    md_lines.append('|--------|------|--------|')
    md_lines.append(f'| **P0 本周** | {complexity_count["simple"] + complexity_count["moderate"]} | ~{(complexity_count["simple"] * 7 + complexity_count["moderate"] * 22) // 60}h |')
    md_lines.append(f'| **P1 下周** | {complexity_count["complex"]} | ~{(complexity_count["complex"] * 45) // 60}h |')
    md_lines.append(f'| **P2 本月** | {complexity_count["very_complex"]} | ~{(complexity_count["very_complex"] * 90) // 60}h |')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('## 三、Spec 详细清单 (按 unsafe 变化降序)')
    md_lines.append('')
    md_lines.append('| # | Spec | 复杂度 | test 数 | 总变化 | safe | unsafe | 行数 | 估时 |')
    md_lines.append('|---|------|--------|--------:|------:|-----:|------:|-----:|------|')
    for i, a in enumerate(analyses, 1):
        eff = estimate_effort(a['complexity'])
        md_lines.append(
            f'| {i} | `{a["spec"]}` | {a["complexity"]} | {a["test_count"]} | '
            f'{a["total_changes"]} | {a["safe_changes"]} | {a["unsafe_changes"]} | '
            f'{a["line_count"]} | {eff} |'
        )
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('## 四、详细问题分布 (按 pattern)')
    md_lines.append('')
    pattern_count = defaultdict(int)
    for a in analyses:
        for d in a['details']:
            pattern_count[d['pattern']] += d['count']
    md_lines.append('| v1 模式 | 出现次数 | 需手动 | 风险 |')
    md_lines.append('|---------|--------:|------:|------|')
    pattern_risk = {
        'pw_import': ('🟢', 'auto-fix'),
        'auth_import': ('🟢', 'auto-fix (删除)'),
        'login_call': ('🟢', 'auto-fix (删除)'),
        'setAdminPermissions_call': ('🟢', 'auto-fix (删除)'),
        'navigateAndWaitForPage': ('🟢', 'auto-fix'),
        'page_goto': ('🟢', 'auto-fix'),
        'waitForTimeout': ('🟡', '需推断 API endpoint'),
        'attachScreenshot': ('🟡', '需重构为 withStep'),
        'el_table_locator': ('🔴', '需 POM 替换'),
        'el_tabs_item': ('🟡', '需 openTab()'),
        'search_input': ('🟡', '需 search()'),
    }
    for pat, count in sorted(pattern_count.items(), key=lambda x: -x[1]):
        risk, hint = pattern_risk.get(pat, ('?', '?'))
        md_lines.append(f'| `{pat}` | {count} | {risk} | {hint} |')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('## 五、试点建议 (P0 优先)')
    md_lines.append('')
    p0_specs = [a for a in analyses if a['complexity'] in ['simple', 'moderate']][:10]
    md_lines.append('### Top 10 最易迁移的 v1 spec (建议先做这 10 个)')
    md_lines.append('')
    for i, a in enumerate(p0_specs, 1):
        md_lines.append(f'{i}. **{a["spec"]}** ({a["complexity"]}, {a["unsafe_changes"]} 手动, 估时 {estimate_effort(a["complexity"])})')
    md_lines.append('')
    md_lines.append('### 迁移步骤 (单个 spec):')
    md_lines.append('```')
    md_lines.append('1. 备份原 spec (git commit 前)')
    md_lines.append('2. 改 import: @playwright/test → auto-fixtures.js')
    md_lines.append('3. 删 v1 helpers import (login, setAdminPermissions, etc.)')
    md_lines.append('4. 在 test 参数加: { page, devLogin, navigateTo, isolation, waitForApiFn, withStep }')
    md_lines.append('5. 删 await login(page) + await setAdminPermissions(page)')
    md_lines.append('6. await navigateAndWaitForPage(...) → await navigateTo(...)')
    md_lines.append('7. await attachScreenshot → withStep 包裹原代码块')
    md_lines.append('8. await page.waitForTimeout → await waitForApiFn(已知 API) 或删除')
    md_lines.append('9. page.locator(".el-table") → 用 POM (archData.getRowCount() 等)')
    md_lines.append('10. 跑 python e2e/scripts/check_v2_compliance.py <spec>')
    md_lines.append('11. 跑 npx playwright test <spec> --retries=0 --project=features 验证')
    md_lines.append('```')
    md_lines.append('')
    md_lines.append('---')
    md_lines.append('')
    md_lines.append('## 六、自动化程度评估')
    md_lines.append('')
    md_lines.append('| 步骤 | 自动程度 | 工具 |')
    md_lines.append('|------|---------|------|')
    md_lines.append('| 1. import 替换 | 🟢 100% | sed/Python regex |')
    md_lines.append('| 2. 删除 login/setAdminPermissions | 🟢 100% | sed/Python regex |')
    md_lines.append('| 3. navigateAndWaitForPage → navigateTo | 🟢 100% | sed/Python regex |')
    md_lines.append('| 4. page.goto → navigateTo | 🟢 100% | sed/Python regex |')
    md_lines.append('| 5. waitForTimeout → waitForApiFn | 🟡 50% | 需 API 信息 |')
    md_lines.append('| 6. attachScreenshot → withStep | 🟡 30% | 需上下文分析 |')
    md_lines.append('| 7. .el-table → POM | 🔴 10% | 需业务理解 |')
    md_lines.append('| 8. .el-tabs → openTab | 🟡 70% | 部分可自动 |')
    md_lines.append('')
    md_lines.append('**结论**: 简单迁移 70% 可自动,POM 重构需人工 (核心价值)。')
    md_lines.append('')

    # 写文件
    Path(output_md).parent.mkdir(parents=True, exist_ok=True)
    Path(output_md).write_text('\n'.join(md_lines), encoding='utf-8')
    Path(output_json).write_text(
        json.dumps({
            'summary': {
                'total': len(v1_specs),
                'total_safe': total_safe,
                'total_unsafe': total_unsafe,
                'complexity': dict(complexity_count),
                'total_minutes': total_minutes,
            },
            'specs': analyses,
        }, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    # 控制台输出
    print(f"[2] 已生成 {output_md}")
    print(f"    已生成 {output_json}")
    print()
    print(f"=== 统计 ===")
    print(f"  v1 spec 总数: {len(v1_specs)}")
    print(f"  总估时: ~{total_minutes // 60}h {total_minutes % 60}min")
    print(f"  复杂度:")
    for c in ['simple', 'moderate', 'complex', 'very_complex']:
        n = complexity_count[c]
        if n > 0:
            print(f"    {c}: {n}")
    print()
    print(f"=== Top 5 P0 (最易迁移) ===")
    for i, a in enumerate(analyses[:5], 1):
        if a['complexity'] in ['simple', 'moderate']:
            print(f"  {i}. {a['spec']} ({a['complexity']}, {a['unsafe_changes']} 手动)")


if __name__ == '__main__':
    main()
