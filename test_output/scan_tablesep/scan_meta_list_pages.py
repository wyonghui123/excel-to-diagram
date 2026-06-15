"""
扫描多个列表页面, 检查 toolbar/table 视觉分离问题 (custom-table class) 是否真的在所有 MetaListPage 实例上都修复了。
"""
import sys
import json
import time
import os

sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

# 调整后的页面 URL (基于实际路由)
pages = [
    ('business_object', '/system/archdata?productId=1&versionId=1&tab=business_object'),
    ('association', '/system/archdata?productId=1&versionId=1&tab=association'),
    ('user_group', '/user-permission?tab=user-groups'),
    ('role', '/user-permission?tab=roles'),
    ('permission_rule', '/system-admin'),  # 最接近的, audit log mgmt 也有 table
]

output_dir = 'd:/filework/excel-to-diagram/test_output/scan_tablesep'
os.makedirs(output_dir, exist_ok=True)

# 全局 JS: 提取 table header 信息
EXTRACT_JS = '''() => {
    // 1. 找第一个可见的 .el-table
    const tables = document.querySelectorAll('.el-table');
    const visibleTables = Array.from(tables).filter(t => {
        const rect = t.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    });

    if (visibleTables.length === 0) {
        return { error: 'no visible .el-table found', countTables: tables.length };
    }

    // 2. 检查是否有 .custom-table
    const customTables = document.querySelectorAll('.custom-table');
    const visibleCustomTables = Array.from(customTables).filter(t => {
        const rect = t.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    });

    // 3. 取第一个 table 的 header
    const firstTable = visibleTables[0];
    const headerCell = firstTable.querySelector('.el-table__header th.el-table__cell') ||
                       firstTable.querySelector('.el-table__header th');
    let headerInfo = null;
    if (headerCell) {
        const cs = window.getComputedStyle(headerCell);
        headerInfo = {
            bg: cs.backgroundColor,
            color: cs.color,
            borderBottom: cs.borderBottomColor,
        };
    }

    // 4. 找 .el-table__header-wrapper (toolbar 区域)
    const headerWrapper = firstTable.querySelector('.el-table__header-wrapper');
    let wrapperInfo = null;
    if (headerWrapper) {
        const cs = window.getComputedStyle(headerWrapper);
        wrapperInfo = {
            bg: cs.backgroundColor,
        };
    }

    // 5. 检查 toolbar 元素 (.list-toolbar, .table-toolbar, .custom-toolbar)
    const toolbar = document.querySelector('.list-toolbar, .table-toolbar, .custom-toolbar, .toolbar, .filter-bar');
    let toolbarInfo = null;
    if (toolbar) {
        const cs = window.getComputedStyle(toolbar);
        const rect = toolbar.getBoundingClientRect();
        toolbarInfo = {
            bg: cs.backgroundColor,
            border: cs.border,
            rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height },
        };
    }

    // 6. CSS variable
    const root = document.documentElement;
    const cssVar = getComputedStyle(root).getPropertyValue('--el-table-header-bg-color').trim();

    // 7. 父级元素是否有 .custom-table 或 .meta-list-page 类
    let parent = firstTable.parentElement;
    let ancestorClasses = [];
    let depth = 0;
    while (parent && depth < 8) {
        ancestorClasses.push({
            tag: parent.tagName,
            class: String(parent.className).slice(0, 100),
        });
        if (parent.classList && parent.classList.contains('custom-table')) break;
        parent = parent.parentElement;
        depth++;
    }

    return {
        url: window.location.href,
        countTables: tables.length,
        countVisibleTables: visibleTables.length,
        countCustomTables: customTables.length,
        countVisibleCustomTables: visibleCustomTables.length,
        hasCustomTable: customTables.length > 0,
        headerBg: headerInfo ? headerInfo.bg : null,
        headerColor: headerInfo ? headerInfo.color : null,
        wrapperBg: wrapperInfo ? wrapperInfo.bg : null,
        cssVar: cssVar || null,
        toolbar: toolbarInfo,
        firstTableClasses: String(firstTable.className).slice(0, 200),
        firstTableParentClasses: ancestorClasses.slice(0, 3),
        title: document.title,
    };
}'''

results = {}
screenshots = {}

print(f"[*] 开始扫描 {len(pages)} 个列表页面...")
print(f"[*] 输出目录: {output_dir}\n")

with PlaywrightCLI(screenshot_dir=output_dir) as cli:
    for name, url in pages:
        print(f"[SCAN] {name}: {url}")
        try:
            # 等待表格出现的超时
            cli.authenticated_navigate(url, timeout=30000)
            # 等待 5s Vite HMR / 数据加载
            time.sleep(5)

            data = cli.evaluate(EXTRACT_JS)
            results[name] = {
                'url': url,
                'data': data,
                'status': 'ok',
            }

            # 截图
            screenshot_path = os.path.join(output_dir, f'scan_{name}.png')
            cli.screenshot(screenshot_path)
            screenshots[name] = screenshot_path

            # 简明输出
            if 'error' in data:
                print(f"  [WARN] {data['error']}")
            else:
                has_ct = data.get('hasCustomTable', False)
                bg = data.get('headerBg', '?')
                css_var = data.get('cssVar', '?')
                tbl_count = data.get('countVisibleTables', 0)
                print(f"  [OK] tables={tbl_count}, customTable={has_ct}, headerBg={bg}, cssVar='{css_var}'")
        except Exception as e:
            results[name] = {
                'url': url,
                'error': str(e)[:300],
                'status': 'fail',
            }
            print(f"  [FAIL] {str(e)[:200]}")

        print()

# 保存报告
report = {
    'scan_time': time.strftime('%Y-%m-%d %H:%M:%S'),
    'total_pages': len(pages),
    'screenshots': screenshots,
    'results': results,
    'summary': {},
}

# 生成修复状态摘要
# "修复" 标准: 存在 .custom-table 类, 且 header bg 不是 transparent 或全白 (比如 rgb(255,255,255) 透明)
# 因为修复是: 在 MetaListPage 根上添加 .custom-table 类, 配 CSS 调整 th 背景
def evaluate_fix(data):
    if 'error' in data:
        return 'no_table'  # 找不到 table
    if not data.get('hasCustomTable'):
        return 'missing_custom_class'  # 没有 custom-table 类, 修复未到位
    bg = data.get('headerBg', '')
    if bg in ('rgba(0, 0, 0, 0)', 'transparent', '', None):
        return 'transparent_bg'  # 透明背景 (Element Plus 默认)
    return 'fixed'  # 修复完成

for name, r in results.items():
    if r.get('status') == 'ok':
        r['fix_status'] = evaluate_fix(r['data'])
    else:
        r['fix_status'] = 'navigation_failed'

# 统计
status_counts = {}
for r in results.values():
    s = r.get('fix_status', 'unknown')
    status_counts[s] = status_counts.get(s, 0) + 1
report['summary'] = status_counts

# 保存
report_path = os.path.join(output_dir, 'scan_report.json')
with open(report_path, 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n{'='*60}")
print(f"[SUMMARY] 修复状态统计:")
for status, count in status_counts.items():
    print(f"  - {status}: {count}")
print(f"{'='*60}")
print(f"\n[REPORT] {report_path}")

# 打印 JSON
print(f"\n[DETAILED JSON]")
print(json.dumps(report, ensure_ascii=False, indent=2))
