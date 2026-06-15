"""
AUTHORITATIVE End-to-End CSS State Verification
================================================

Authoritative measurement of 5 key CSS states (normal / hover / sort-active
/ table-empty / row-hover) for the toolbar and th elements on the
MetaListPage component.

Pages tested (consistency check):
  1. /product-management     (target page)
  2. /system/archdata?tab=association
  3. /system/archdata?tab=business
  4. /system/permission/users

Saves:
  - AUTHORITATIVE_<page>.png  full-page screenshots
  - AUTHORITATIVE_results.json  detailed measurements

Author: Sub-agent (AUTHORITATIVE verification)
Date: 2026-06-13
"""
import json
import sys
import time
import os

# 调整 path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# 脚本位于 test_helpers/scripts/，需要往上两层到项目根
PROJECT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', '..'))
sys.path.insert(0, PROJECT_DIR)

from test_helpers.browser_auth_cli import PlaywrightCLI

OUTPUT_DIR = os.path.join(PROJECT_DIR, 'test_output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

URLS_TO_TEST = [
    '/product-management',
    '/system/archdata?tab=association',
    '/system/archdata?tab=business',
    '/system/permission/users',
]

TARGET_PAGE = '/product-management'

# ----------------------------------------------------------------------
# JS 评估代码
# ----------------------------------------------------------------------
EVAL_NORMAL = r"""() => {
    const ths = document.querySelectorAll('.custom-table .el-table__header th.el-table__cell');
    const tb = document.querySelector('.meta-list-page .toolbar');
    if (!ths.length) {
        return {error: 'no th elements found (.custom-table .el-table__header th.el-table__cell)'};
    }
    const cs0 = window.getComputedStyle(ths[0]);
    return {
        thCount: ths.length,
        firstTh: {
            backgroundColor: cs0.backgroundColor,
            borderBottom: cs0.borderBottom,
            color: cs0.color,
            fontWeight: cs0.fontWeight,
            height: Math.round(ths[0].getBoundingClientRect().height)
        },
        toolbar: tb ? (() => {
            const cs = getComputedStyle(tb);
            return {
                backgroundColor: cs.backgroundColor,
                borderBottom: cs.borderBottom,
                padding: cs.padding,
                height: Math.round(tb.getBoundingClientRect().height)
            };
        })() : null
    };
}"""

EVAL_TH_STYLE = r"""() => {
    const t = document.querySelector('.custom-table .el-table__header th.el-table__cell');
    if (!t) return {error: 'no th'};
    const cs = getComputedStyle(t);
    return {
        backgroundColor: cs.backgroundColor,
        color: cs.color,
        borderBottom: cs.borderBottom
    };
}"""

EVAL_TR_STYLE = r"""() => {
    const trs = document.querySelectorAll('.custom-table .el-table__body tr.el-table__row');
    if (!trs.length) return {error: 'no rows'};
    const cs = getComputedStyle(trs[0]);
    return {
        rowCount: trs.length,
        backgroundColor: cs.backgroundColor,
        borderBottom: cs.borderBottom,
        height: Math.round(trs[0].getBoundingClientRect().height)
    };
}"""

EVAL_SORT_ACTIVE = r"""() => {
    // 找带 is-sortable / sort-active / ascending / descending class 的 th
    const candidates = document.querySelectorAll(
        '.custom-table .el-table__header th.el-table__cell'
    );
    let found = null;
    for (const t of candidates) {
        if (
            t.classList.contains('is-sortable') ||
            t.classList.contains('is-sorted') ||
            t.classList.contains('ascending') ||
            t.classList.contains('descending') ||
            t.querySelector('.caret-wrapper.is-active') ||
            t.querySelector('.sort-caret.ascending') ||
            t.querySelector('.sort-caret.descending')
        ) {
            found = t;
            break;
        }
    }
    if (!found) {
        return {sortActiveFound: false, sortedThCount: 0};
    }
    const cs = getComputedStyle(found);
    return {
        sortActiveFound: true,
        backgroundColor: cs.backgroundColor,
        color: cs.color,
        classes: Array.from(found.classList).join(' ')
    };
}"""

EVAL_TABLE_EMPTY = r"""() => {
    // empty 状态：el-table__empty-block 存在 + 没有 row
    const empty = document.querySelector('.custom-table .el-table__empty-block');
    const rows = document.querySelectorAll('.custom-table .el-table__body tr.el-table__row');
    if (!empty) {
        return {emptyBlockExists: false, rowCount: rows.length};
    }
    const cs = getComputedStyle(empty);
    return {
        emptyBlockExists: true,
        rowCount: rows.length,
        backgroundColor: cs.backgroundColor,
        color: cs.color,
        height: Math.round(empty.getBoundingClientRect().height),
        text: (empty.textContent || '').trim().slice(0, 80)
    };
}"""


# ----------------------------------------------------------------------
# 测量逻辑
# ----------------------------------------------------------------------
def measure_state_normal(cli):
    """State 1: 正常态 - 无 hover / sort / hover-row"""
    return cli.evaluate(EVAL_NORMAL)


def measure_state_hover(cli):
    """State 2: hover on th"""
    # 先把鼠标移开（移动到左上角），避免上次 hover 影响
    cli.evaluate("() => { document.body.style.cursor = 'default'; }")
    cli._page.mouse.move(0, 0)
    time.sleep(0.3)
    # 检查是否存在
    count = cli._page.locator('.custom-table .el-table__header th.el-table__cell').count()
    if count == 0:
        return {'skipped': True, 'reason': 'no .custom-table th elements on this page'}
    # hover first th
    th_locator = cli._page.locator('.custom-table .el-table__header th.el-table__cell').first
    try:
        th_locator.hover(force=True, timeout=5000)
    except Exception as e:
        return {'error': f'hover th failed: {e}'}
    time.sleep(0.5)
    return cli.evaluate(EVAL_TH_STYLE)


def measure_state_sort_active(cli):
    """State 3: 排序激活态 - 点击 th 触发 sort，再测"""
    cli._page.mouse.move(0, 0)
    time.sleep(0.3)
    # 找 sortable th
    sortable_count = cli._page.locator(
        '.custom-table .el-table__header th.el-table__cell.is-sortable'
    ).count()
    if sortable_count == 0:
        return {'skipped': True, 'reason': 'no sortable th on this page'}
    th_locator = cli._page.locator(
        '.custom-table .el-table__header th.el-table__cell.is-sortable'
    ).first
    try:
        th_locator.click(timeout=5000)
        time.sleep(0.8)
        return cli.evaluate(EVAL_SORT_ACTIVE)
    except Exception as e:
        return {'error': f'click sortable th failed: {e}'}


def measure_state_table_empty(cli):
    """State 4: empty 态 - 被动检查当前是否为空"""
    cli._page.mouse.move(0, 0)
    time.sleep(0.3)
    return cli.evaluate(EVAL_TABLE_EMPTY)


def measure_state_row_hover(cli):
    """State 5: row hover - hover first row"""
    cli._page.mouse.move(0, 0)
    time.sleep(0.3)
    row_count = cli._page.locator(
        '.custom-table .el-table__body tr.el-table__row'
    ).count()
    if row_count == 0:
        return {'skipped': True, 'reason': 'no rows to hover'}
    row_locator = cli._page.locator(
        '.custom-table .el-table__body tr.el-table__row'
    ).first
    try:
        row_locator.hover(force=True, timeout=5000)
    except Exception as e:
        return {'error': f'hover row failed: {e}'}
    time.sleep(0.5)
    return cli.evaluate(EVAL_TR_STYLE)


def measure_page_full(cli, url):
    """
    对一个 URL 测量所有 5 个状态
    """
    print(f'\n=== Measuring: {url} ===')
    # Try SPA navigation first
    nav_ok = False
    try:
        cli.authenticated_navigate(
            url,
            wait_for_selector='.meta-list-page, .el-table, .custom-table, #app',
            timeout=45000
        )
        nav_ok = True
    except Exception as e:
        print(f'  [WARN] SPA nav failed for {url}: {e}; trying direct goto')
        try:
            cli._page.goto(f'http://localhost:3004{url}', wait_until='domcontentloaded', timeout=30000)
            time.sleep(5)
            nav_ok = True
        except Exception as e2:
            print(f'  [ERROR] direct goto also failed: {e2}')
            return {'url': url, 'states': {'nav_error': str(e2)}}

    # Vite HMR settle
    time.sleep(7)
    # 等待表格可见
    try:
        cli.wait_for_selector('.custom-table', timeout=10000)
    except Exception:
        print(f'  [WARN] .custom-table not visible for {url}')

    states = {}

    # 1. Normal
    states['normal'] = measure_state_normal(cli)
    print(f'  [1/5] normal: {json.dumps(states["normal"], ensure_ascii=False)[:200]}')

    # 2. Hover (th)
    states['hover'] = measure_state_hover(cli)
    print(f'  [2/5] hover: {json.dumps(states["hover"], ensure_ascii=False)[:200]}')

    # 3. Sort active
    states['sort_active'] = measure_state_sort_active(cli)
    print(f'  [3/5] sort_active: {json.dumps(states["sort_active"], ensure_ascii=False)[:200]}')

    # 4. Table empty (passive: check current state; do not mutate data)
    states['table_empty'] = measure_state_table_empty(cli)
    print(f'  [4/5] table_empty: {json.dumps(states["table_empty"], ensure_ascii=False)[:200]}')

    # 5. Row hover
    states['row_hover'] = measure_state_row_hover(cli)
    print(f'  [5/5] row_hover: {json.dumps(states["row_hover"], ensure_ascii=False)[:200]}')

    return {'url': url, 'states': states}


def screenshot_page(cli, url, filename):
    """对当前页面做 full_page 截图"""
    try:
        cli.authenticated_navigate(
            url,
            wait_for_selector='.meta-list-page, .el-table, .custom-table',
            timeout=45000
        )
    except Exception as e:
        print(f'  [WARN] SPA nav for screenshot {url} failed: {e}; fallback to direct goto')
        cli._page.goto(f'http://localhost:3004{url}', wait_until='domcontentloaded', timeout=30000)
    time.sleep(7)
    try:
        cli.wait_for_selector('.custom-table', timeout=10000)
    except Exception:
        pass
    # 重定向路径（避免 / 在文件名造成路径问题）
    safe_name = url.replace('/', '_').replace('?', '_').replace('=', '_')
    fname = f'AUTHORITATIVE_{filename}.png'
    path = os.path.join(OUTPUT_DIR, fname)
    cli.screenshot(fname, full_page=True)
    actual = os.path.join(os.getcwd(), 'test_output', fname)
    print(f'  [SAVED] {fname} (expected at: {path} | actual: {actual})')
    return fname, actual


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    print('=' * 70)
    print('AUTHORITATIVE CSS State Verification')
    print('=' * 70)

    all_results = []
    with PlaywrightCLI() as cli:
        for url in URLS_TO_TEST:
            result = measure_page_full(cli, url)
            all_results.append(result)

        # 对 4 个 URL 各自拍 full-page 截图
        print('\n=== Capturing full-page screenshots ===')
        for i, url in enumerate(URLS_TO_TEST):
            slug = url.strip('/').replace('/', '_').replace('?', '_').replace('=', '_').replace(':', '_') or 'root'
            slug = slug[:60]
            try:
                fname, actual = screenshot_page(cli, url, f'p{i+1}_{slug}')
                all_results[i]['screenshot'] = fname
                all_results[i]['screenshot_path'] = actual
            except Exception as e:
                print(f'  [ERROR] screenshot {url} failed: {e}')
                all_results[i]['screenshot_error'] = str(e)

    # 写结果
    json_path = os.path.join(OUTPUT_DIR, 'AUTHORITATIVE_results.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f'\n[SAVED] {json_path}')

    # 总结
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    for r in all_results:
        url = r['url']
        s = r['states']
        n = s.get('normal', {})
        h = s.get('hover', {})
        sa = s.get('sort_active', {})
        ft = n.get('firstTh', {}) if isinstance(n, dict) else {}
        tb = n.get('toolbar') if isinstance(n, dict) else None
        print(f"\n[{url}]")
        if ft:
            print(f"  th.bg = {ft.get('backgroundColor')}")
            print(f"  th.border-bottom = {ft.get('borderBottom')}")
            print(f"  th.height = {ft.get('height')}px")
        if tb:
            print(f"  toolbar.bg = {tb.get('backgroundColor')}")
            print(f"  toolbar.border-bottom = {tb.get('borderBottom')}")
        if isinstance(h, dict) and 'backgroundColor' in h:
            print(f"  hover-th.bg = {h.get('backgroundColor')}")
        if isinstance(sa, dict) and sa.get('sortActiveFound'):
            print(f"  sort-active.bg = {sa.get('backgroundColor')}")
        else:
            print(f"  sort-active: not found / not active")
        if 'screenshot' in r:
            print(f"  screenshot: {r['screenshot']}")

    return all_results


if __name__ == '__main__':
    main()
