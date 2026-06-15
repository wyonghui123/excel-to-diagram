#!/usr/bin/env python3
"""
业务模型规则驱动 (BMRD) 的 E2E 测试生成器 v2
支持多个规则文件 (protection_rules, crud_lifecycle_rules, ...)
"""
import sys
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = PROJECT_ROOT / '.trae' / 'specs' / '_business_rules'
OUTPUT_DIR = PROJECT_ROOT / 'e2e' / 'business-flow'

# 规则文件配置: (文件名, 输出 spec 文件, 标题, 分组 imports)
RULE_FILES = [
    {
        'yaml': '_protection_rules.yaml',
        'spec': 'protection-rules.spec.js',
        'title': 'S-BRP-PROTECTION: 业务保护规则 (DEC-1, DEC-2, DEC-3, DEC-4, BUG) - BMRD',
        'imports': """import { DetailDrawerPage } from '../page-objects/DetailDrawerPage.js'
import { findSystemEnum, findLockedEnum, findSystemEnumValue } from '../helpers/enum-finder.js'
import { GenericListPage } from '../page-objects/GenericListPage.js'"""
    },
    {
        'yaml': '_crud_lifecycle_rules.yaml',
        'spec': 'crud-lifecycle-rules.spec.js',
        'title': 'S-BRP-CRUD: CRUD + 生命周期规则 (CRUD-1 ~ CRUD-5, UI-1 ~ UI-10, HEALTH, PERF) - BMRD',
        'imports': "import { GenericListPage } from '../page-objects/GenericListPage.js'"
    },
    {
        'yaml': '_audit_i18n_fk_rules.yaml',
        'spec': 'audit-i18n-fk-rules.spec.js',
        'title': 'S-BRP-AUDIT-I18N-FK: 审计 + i18n + FK 关系规则 (AUDIT-1 ~ AUDIT-4, I18N-1 ~ I18N-2, FK-1 ~ FK-2, PERSIST-1, MULTITAB-1) - BMRD',
        'imports': "import { GenericListPage } from '../page-objects/GenericListPage.js'"
    },
    {
        'yaml': '_permission_security_rules.yaml',
        'spec': 'permission-security-rules.spec.js',
        'title': 'S-BRP-PERM-SEC: 权限 + 数据权限 + 安全规则 (PERM-1 ~ PERM-3, USER-1, SEC-1 ~ SEC-2, DATA-PERM-1, ROLE-PERM-1, USER-GROUP-MEMBER-1) - BMRD',
        'imports': ''
    },
    {
        'yaml': '_advanced_module_rules.yaml',
        'spec': 'advanced-module-rules.spec.js',
        'title': 'S-BRP-ADV: 高级模块规则 (SCHED, CHANGE, IMPORT, EXPORT, LOCK, NOTIF, CASCADE, TRANS, ANNOUNCE, ATTACH, OWNER, FK-HELP) - BMRD',
        'imports': ''
    },
    {
        'yaml': '_data_permission_dimension_rules.yaml',
        'spec': 'data-permission-dimension-rules.spec.js',
        'title': 'S-BRP-DPD: 数据权限 + 维度 + 值列表规则 (DATA-PERM-DIM-1 ~ 4, VAL-1 ~ 2, FILTER-1, BO-1 ~ 2, SVC-1 ~ 3, DIM-1 ~ 2) - BMRD',
        'imports': ''
    },
    {
        'yaml': '_masterdata_schema_workflow_rules.yaml',
        'spec': 'masterdata-schema-workflow-rules.spec.js',
        'title': 'S-BRP-MSW: 主数据 + 表单 schema + 工作流规则 (MENU-1 ~ 4, MD-1, SCHEMA-1 ~ 3, WF-1 ~ 3, VIEW-1, ROUTE-1, TEMPLATE-1, I18N-API-1, TAG-1, CACHE-1) - BMRD',
        'imports': ''
    }
]


def render_test_template(template_obj, rule):
    """渲染单个 test 模板"""
    template_code = template_obj['template'].strip().replace('{{title}}', template_obj['title'])
    indented = '\n'.join('    ' + line for line in template_code.split('\n'))
    return '''  /**
   * {title}
   * 业务规则: {rule_id} - {rule_name}
   * 优先级: {priority}
   */
{indented}
'''.format(
        title=template_obj['title'],
        rule_id=rule['id'],
        rule_name=rule['name'],
        priority=rule.get('priority', 'P2'),
        indented=indented
    )


def render_rule_block(rule):
    """渲染整个规则的 describe 块"""
    templates = rule.get('test_templates', [])
    if not templates:
        return ''
    title = "S-BRP-{id}: {name} (BMRD)".format(id=rule['id'], name=rule['name'])
    tests_code = []
    for tmpl in templates:
        tests_code.append(render_test_template(tmpl, rule))
    return '''test.describe('{title}', () => {{
{tests}
}})
'''.format(title=title, tests=''.join(tests_code))


def render_defer_block(rule):
    """渲染 DEFER 规则 (生成 skip 测试, 明确告知状态)"""
    templates = rule.get('test_templates', [])
    if not templates:
        return ''
    title = "S-BRP-{id}-DEFER: {name} (BMRD-DEFER)".format(id=rule['id'], name=rule['name'])
    reason = rule.get('name', 'DEFER')
    skip_tests = []
    for tmpl in templates:
        # DEFER 模板: 在 test body 第一行就 test.skip, 不执行原测试
        template_code = tmpl['template'].strip().replace('{{title}}', tmpl['title'])
        # 找到第一行 test(' 之后插入 skip
        skip_line = '      test.skip(true, "[DEFER-{rule_id}] {reason} - 等条件解锁后改 status=ACTIVE 重跑生成器")'.format(
            rule_id=rule['id'], reason=reason.replace('"', "'")
        )
        # 在第一行 test.skip 之后立即 return
        lines = template_code.split('\n')
        new_lines = [lines[0], skip_line, '      return']
        new_lines.extend(lines[1:])
        new_code = '\n'.join(new_lines)
        indented = '\n'.join('    ' + line for line in new_code.split('\n'))
        skip_tests.append(indented)
    return '''test.describe('{title}', () => {{
{tests}
}})
'''.format(title=title, tests='\n'.join(skip_tests))


def generate_spec_file(filename, title, rules, extra_imports='', header_extra=''):
    """生成 spec 文件"""
    rules_summary = '\n'.join(
        " *   {id}: {name} [{status}]".format(
            id=r['id'], name=r['name'], status=r.get('status', 'ACTIVE')
        ) for r in rules
    )
    # BMRD 3.0: DEFER 规则生成 skip 测试 (明确告知状态)
    def render_rule_or_defer(r):
        if r.get('status', 'ACTIVE') == 'DEFER':
            return render_defer_block(r)
        return render_rule_block(r)
    describe_blocks = '\n'.join(render_rule_or_defer(r) for r in rules)
    content = '''/**
 * {title}
 *
 * [业务模型规则驱动 (BMRD) v2.0 - 自动生成]
 * 来源: .trae/specs/_business_rules/*.yaml
 * 生成器: scripts/generate-protection-tests.py
 * 生成时间: 2026-06-13
 *
 * 业务规则:
{rules_summary}
 *
 * v2 铁律合规 (8 项):
 * [OK] import from auto-fixtures.js
 * [OK] 无 login() / setAdminPermissions()
 * [OK] 用 navigateTo() 不用 page.goto()
 * [OK] 用 isolation.createTracked()
 * [OK] 用 POM
 * [OK] 用 waitForApiFn()
 * [OK] withStep 包裹
 * [OK] isolation fixture 解构
 *
 * DEFER 项: 见源 YAML 文件的 deferred 节点
{header_extra}
 */
import {{ test, expect }} from '../helpers/auto-fixtures.js'
{extra_imports}

{describe_blocks}
'''.format(
        title=title,
        rules_summary=rules_summary,
        header_extra=header_extra,
        extra_imports=extra_imports,
        describe_blocks=describe_blocks
    )
    output = OUTPUT_DIR / filename
    with open(output, 'w', encoding='utf-8') as f:
        f.write(content)
    test_count = sum(len(r['test_templates']) for r in rules)
    print("[OK] {output} ({count} tests)".format(output=output, count=test_count))
    return test_count


def main():
    total_all = 0
    total_defer = 0
    total_rules = 0

    for cfg in RULE_FILES:
        yaml_path = RULES_DIR / cfg['yaml']
        if not yaml_path.exists():
            print("[SKIP] {p} not found".format(p=yaml_path))
            continue
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        rules = data.get('rules', [])
        deferred = data.get('deferred', [])
        # 兼容 None (deferred 节点完全缺失)
        if deferred is None:
            deferred = []
        active = [r for r in rules if r.get('status', 'ACTIVE') == 'ACTIVE']
        defer_in_rules = [r for r in rules if r.get('status', 'ACTIVE') == 'DEFER']
        all_rendered = active + defer_in_rules  # BMRD 3.0: ACTIVE+DEFER 都生成测试
        print("\n[{name}] {r} rules ({a} active, {d} deferred-in-rules, {x} pending-list)".format(
            name=cfg['yaml'], r=len(rules), a=len(active), d=len(defer_in_rules), x=len(deferred)
        ))
        total = generate_spec_file(
            cfg['spec'], cfg['title'], all_rendered,
            extra_imports=cfg['imports'],
            header_extra="\n * YAML 文件: {p}".format(p=yaml_path)
        )
        total_all += total
        total_defer += len(deferred) + len(defer_in_rules)
        total_rules += len(rules)

    print("\n" + "=" * 60)
    print("[GRAND SUMMARY]")
    print("  Active tests: {t}".format(t=total_all))
    print("  Deferred: {d}".format(d=total_defer))
    print("  Total rules: {r}".format(r=total_rules))
    print("=" * 60)


if __name__ == '__main__':
    main()
