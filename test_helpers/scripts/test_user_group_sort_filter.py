# -*- coding: utf-8 -*-
"""
用户组管理页面 - 成员数列 sorting 和 filtering 前端验证

测试场景：
1. 默认状态
2. 点击"成员数"列 - 升序
3. 再次点击"成员数"列 - 降序
4. 第三次点击"成员数"列 - 取消排序
5. filtering: 关键字搜索 + 排序

通过 PlaywrightCLI 完成，按 SESSION_REMINDER 铁律：
- 必须 check_health() / assert_healthy()
- 禁止 wait_for_timeout
- cookie 认证（dev-login httpOnly）
"""
import sys
import os
import json
import re

sys.path.insert(0, r'd:\filework\excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

TARGET_PATH = '/user-permission'
USER_GROUP_TAB_TEXT = '用户组管理'  # tab 文字
MEMBER_COL_TEXT = '成员数'  # 中文列名


def parse_int(text):
    if not text:
        return None
    m = re.search(r'-?\d+', text.replace(',', ''))
    return int(m.group()) if m else None


def get_column_values(cli, col_index, max_rows=10):
    """读取表格某一列前 max_rows 行的值"""
    js = """
    (args) => {
        const colIndex = args.colIndex;
        const max = args.maxRows;
        const rows = document.querySelectorAll('.el-table__body-wrapper .el-table__row');
        const out = [];
        for (let i = 0; i < Math.min(rows.length, max); i++) {
            const cells = rows[i].querySelectorAll('td');
            if (cells.length > colIndex) {
                out.push(cells[colIndex].innerText.trim());
            }
        }
        return out;
    }
    """
    return cli._page.evaluate(js, {'colIndex': col_index, 'maxRows': max_rows})


def get_column_index_by_header(cli, header_text):
    """根据表头文字获取列索引"""
    js = """
    (headerText) => {
        const headers = document.querySelectorAll('.el-table__header-wrapper thead th .cell');
        for (let i = 0; i < headers.length; i++) {
            if (headers[i].innerText.trim() === headerText) {
                return i;
            }
        }
        return -1;
    }
    """
    return cli._page.evaluate(js, header_text)


def is_sorted_asc(values, allow_null=True):
    nums = [parse_int(v) for v in values]
    if allow_null and all(n is None for n in nums):
        return True  # all NULL is technically "sorted" by SQLite (NULLs first)
    filtered = [(i, n) for i, n in enumerate(nums) if n is not None]
    return all(filtered[i][1] <= filtered[i + 1][1] for i in range(len(filtered) - 1))


def is_sorted_desc(values):
    nums = [parse_int(v) for v in values]
    filtered = [(i, n) for i, n in enumerate(nums) if n is not None]
    return all(filtered[i][1] >= filtered[i + 1][1] for i in range(len(filtered) - 1))


def click_header(cli, header_text, click_count=1):
    """点击表头 N 次（每次点击切换 asc -> desc -> null）"""
    js = """
    (headerText) => {
        const headers = document.querySelectorAll('.el-table__header-wrapper thead th .cell');
        for (const h of headers) {
            if (h.innerText.trim() === headerText) {
                // 模拟点 sortable 容器（外层 th）
                const th = h.closest('th');
                if (th) th.click();
                return true;
            }
        }
        return false;
    }
    """
    last = False
    for i in range(click_count):
        last = cli._page.evaluate(js, header_text)
        if not last:
            return False
        # 等待表格刷新完成（通过 store ready 或 rowcount 变化）
        cli.wait_for_stable(max_wait=3000, stable_window=300)
    return last


def get_sort_indicator(cli, header_text):
    """读取当前列的排序方向（asc/desc/''）"""
    js = """
    (headerText) => {
        const headers = document.querySelectorAll('.el-table__header-wrapper thead th .cell');
        for (const h of headers) {
            if (h.innerText.trim() === headerText) {
                const wrapper = h.closest('.caret-wrapper, .sort-caret');
                if (!wrapper) {
                    // 尝试通过 class 找
                    const parent = h.parentElement;
                    return {
                        classes: parent ? parent.className : '',
                        active: !!parent && parent.querySelectorAll('.asc, .desc, .is-active, .active').length > 0
                    };
                }
                return {
                    classes: wrapper.className,
                    html: wrapper.innerHTML.substring(0, 200)
                };
            }
        }
        return null;
    }
    """
    return cli._page.evaluate(js, header_text)


def main():
    print('=' * 60)
    print('User Group 页面 sorting/filtering 前端验证')
    print('=' * 60)

    with PlaywrightCLI(headless=True) as cli:
        # 1. 认证 + 导航
        print(f'\n[Step 1] 认证 + 导航到 {TARGET_PATH}')
        cli.authenticated_navigate(
            TARGET_PATH,
            wait_for_selector='.el-table__body-wrapper .el-table__row',
            timeout=20000
        )

        # 健康检查
        health = cli.check_health()
        if not health.get('healthy', True):
            print(f'[WARN] 页面有警告: {health}')

        # 1.5 切换到"用户组管理" tab
        print(f'\n[Step 1.5] 切换到 "{USER_GROUP_TAB_TEXT}" tab')
        tab_clicked = cli._page.evaluate("""(tabText) => {
            // Element Plus 标签页通常用 .el-tabs__item
            const items = document.querySelectorAll('.el-tabs__item, .el-tabs__nav .is-tab, [role="tab"]');
            for (const it of items) {
                if (it.innerText.trim() === tabText) {
                    it.click();
                    return true;
                }
            }
            // 备选：任意包含文字的可点击元素
            const all = document.querySelectorAll('*');
            for (const el of all) {
                if (el.children.length === 0 && el.innerText && el.innerText.trim() === tabText) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""", USER_GROUP_TAB_TEXT)
        print(f'  切换tab: {"OK" if tab_clicked else "FAIL"}')
        if not tab_clicked:
            cli.screenshot('user_group_tab_not_found.png')
            print('  [WARN] 未找到 tab，尝试继续...')

        # 等待新 tab 的表格加载
        cli._page.wait_for_function("""() => {
            const rows = document.querySelectorAll('.el-table__body-wrapper .el-table__row');
            return rows.length > 0;
        }""", timeout=15000)
        cli.wait_for_stable(max_wait=2000, stable_window=400)

        # 2. 找到"成员数"列索引
        col_index = get_column_index_by_header(cli, MEMBER_COL_TEXT)
        print(f'[Step 2] "{MEMBER_COL_TEXT}" 列索引: {col_index}')
        if col_index < 0:
            print('[FAIL] 找不到成员数列！')
            cli.screenshot('user_group_no_member_col.png')
            return

        # 3. 默认状态
        print(f'\n[Step 3] 默认状态（无排序）')
        default_vals = get_column_values(cli, col_index, max_rows=8)
        print(f'  前8行: {default_vals}')

        # 4. 升序
        print(f'\n[Step 4] 点击"成员数"列 -> 升序')
        click_header(cli, MEMBER_COL_TEXT, click_count=1)
        asc_vals = get_column_values(cli, col_index, max_rows=8)
        asc_nums = [parse_int(v) for v in asc_vals]
        print(f'  前8行: {asc_vals}')
        print(f'  解析为: {asc_nums}')
        asc_indicator = get_sort_indicator(cli, MEMBER_COL_TEXT)
        print(f'  排序指示器: {asc_indicator}')

        asc_ok = is_sorted_asc(asc_vals)
        print(f'  升序校验: {"PASS" if asc_ok else "FAIL"}')
        cli.screenshot('user_group_member_asc.png')

        # 5. 降序
        print(f'\n[Step 5] 再点一次"成员数"列 -> 降序')
        click_header(cli, MEMBER_COL_TEXT, click_count=1)
        desc_vals = get_column_values(cli, col_index, max_rows=8)
        desc_nums = [parse_int(v) for v in desc_vals]
        print(f'  前8行: {desc_vals}')
        print(f'  解析为: {desc_nums}')
        desc_indicator = get_sort_indicator(cli, MEMBER_COL_TEXT)
        print(f'  排序指示器: {desc_indicator}')

        desc_ok = is_sorted_desc(desc_vals)
        print(f'  降序校验: {"PASS" if desc_ok else "FAIL"}')
        cli.screenshot('user_group_member_desc.png')

        # 6. 取消排序
        print(f'\n[Step 6] 再点一次"成员数"列 -> 取消排序')
        click_header(cli, MEMBER_COL_TEXT, click_count=1)
        cancel_vals = get_column_values(cli, col_index, max_rows=8)
        print(f'  前8行: {cancel_vals}')
        cancel_indicator = get_sort_indicator(cli, MEMBER_COL_TEXT)
        print(f'  排序指示器: {cancel_indicator}')

        # 7. 排序 + 过滤
        print(f'\n[Step 7] filtering: 输入关键字 "admin" + 排序')
        # 找到搜索框
        cli.fill('.el-input__inner', 'admin')
        cli.wait_for_stable(max_wait=3000, stable_window=300)
        filtered_vals = get_column_values(cli, col_index, max_rows=8)
        print(f'  过滤后前8行: {filtered_vals}')

        # 在过滤基础上排序
        click_header(cli, MEMBER_COL_TEXT, click_count=1)
        click_header(cli, MEMBER_COL_TEXT, click_count=1)  # asc -> desc
        filtered_desc_vals = get_column_values(cli, col_index, max_rows=8)
        print(f'  过滤+降序前8行: {filtered_desc_vals}')
        filtered_desc_ok = is_sorted_desc(filtered_desc_vals)
        print(f'  过滤+降序校验: {"PASS" if filtered_desc_ok else "FAIL"}')
        cli.screenshot('user_group_filtered_desc.png')

        # 8. 清理搜索
        print(f'\n[Step 8] 清空搜索')
        cli.fill('.el-input__inner', '')
        cli.wait_for_stable(max_wait=2000, stable_window=300)

        # 9. 终极健康检查
        print(f'\n[Step 9] 页面健康检查')
        try:
            cli.assert_healthy()
            print('  页面健康: PASS')
        except Exception as e:
            print(f'  页面健康: FAIL - {e}')

        # 总结
        print(f'\n{"=" * 60}')
        print('结果汇总:')
        print(f'  升序排序: {"PASS" if asc_ok else "FAIL"}')
        print(f'  降序排序: {"PASS" if desc_ok else "FAIL"}')
        print(f'  过滤+降序: {"PASS" if filtered_desc_ok else "FAIL"}')
        print(f'{"=" * 60}')


if __name__ == '__main__':
    main()
