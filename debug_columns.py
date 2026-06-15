# -*- coding: utf-8 -*-
"""
[DEBUG] 检查前端 columnsOverride 是否正确
"""
import time
import sys
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    cli = PlaywrightCLI(headless=False)  # 非 headless，方便调试

    with cli:
        cli.authenticated_navigate('/')
        time.sleep(1)
        page = cli._page

        print('=' * 60)
        print('[访问] /detail/role/1803')
        print('=' * 60)
        page.goto('http://localhost:3004/detail/role/1803', wait_until='domcontentloaded')
        time.sleep(2)

        # 切到"权限配置" + "管理维度范围"
        try:
            page.click('text=权限配置', timeout=3000)
            time.sleep(1)
        except Exception:
            pass
        try:
            page.click('text=管理维度范围', timeout=3000)
            time.sleep(1)
        except Exception:
            pass

        # 点"添加版本"
        try:
            page.click('button:has-text("添加版本")', timeout=3000)
            time.sleep(2)
        except Exception as e:
            print(f'  [X] 找不到按钮: {e}')
            return

        # 检查表头
        print()
        print('=' * 60)
        print('[表头列]')
        print('=' * 60)
        headers = page.evaluate('''() => {
            const ths = document.querySelectorAll('.el-table__header th');
            return Array.from(ths).map(th => th.textContent.trim());
        }''')
        for i, h in enumerate(headers, 1):
            print(f'  #{i}: {h}')

        # 检查表格第一行
        print()
        print('=' * 60)
        print('[第一行数据]')
        print('=' * 60)
        first_row = page.evaluate('''() => {
            const tds = document.querySelectorAll('.el-table__body tr:first-child td');
            return Array.from(tds).map(td => td.textContent.trim());
        }''')
        for i, cell in enumerate(first_row, 1):
            print(f'  #{i}: {cell}')

        # 等待用户查看
        print()
        print('[按 Enter 关闭浏览器]')
        input()


main()
