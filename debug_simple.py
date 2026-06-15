"""
简化测试 - 直接看版本下拉打开后的内容
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    print('=== Step 1: 打开架构数据管理 ===')
    cli.authenticated_navigate('/system/archdata')
    cli.wait_for_stable(2500)

    # 选产品
    print('\n=== Step 2: 选产品 ===')
    cli.evaluate('''() => {
        document.querySelectorAll('.el-select')[0].querySelector('.el-select__wrapper').click()
    }''')
    cli.wait_for_stable(1200)
    cli.evaluate('''() => {
        for (const d of document.querySelectorAll('.el-select-dropdown')) {
            if (d.checkVisibility && d.checkVisibility()) {
                const items = d.querySelectorAll('.el-select-dropdown__item')
                if (items[0]) { items[0].click(); return }
            }
        }
    }''')
    cli.wait_for_stable(2500)
    print('  [OK] 选完产品')

    # 关键：看版本下拉
    print('\n=== Step 3: 打开版本下拉，看内容 ===')
    cli.evaluate('''() => {
        document.querySelectorAll('.el-select')[1].querySelector('.el-select__wrapper').click()
    }''')
    cli.wait_for_stable(1500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/simple_version_dropdown.png')

    version_options = cli.evaluate('''() => {
        const dropdowns = document.querySelectorAll('.el-select-dropdown')
        const results = []
        for (const d of dropdowns) {
            if (d.checkVisibility && d.checkVisibility()) {
                const items = d.querySelectorAll('.el-select-dropdown__item')
                for (const i of items) {
                    results.push(i.textContent.trim())
                }
            }
        }
        return results
    }''')
    print(f'  版本下拉里的内容: {version_options}')

    if not version_options:
        print('  [WARN] 版本下拉是空的！用户根本选不到版本')
        # 关闭下拉
        cli.evaluate('''() => {
            document.body.click()
        }''')
        cli.wait_for_stable(500)
    else:
        # 选第一个版本
        cli.evaluate('''() => {
            for (const d of document.querySelectorAll('.el-select-dropdown')) {
                if (d.checkVisibility && d.checkVisibility()) {
                    const items = d.querySelectorAll('.el-select-dropdown__item')
                    if (items[0]) { items[0].click(); return }
                }
            }
        }''')
        cli.wait_for_stable(2500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/simple_version_selected.png')
        print('  [OK] 选完版本')

    # 看页面状态
    print('\n=== Step 4: 检查页面状态 ===')
    state = cli.evaluate('''() => {
        return {
            url: window.location.href,
            selectStates: Array.from(document.querySelectorAll('.el-select')).map((s, i) => ({
                idx: i,
                placeholder: s.querySelector('.el-select__placeholder')?.textContent?.trim() || '',
                wrap: s.querySelector('.el-select__wrapper')?.textContent?.trim() || ''
            })),
            tabs: Array.from(document.querySelectorAll('.el-tabs__item')).map(t => t.textContent.trim()),
            hintText: document.querySelector('.arch-workspace-hint, .workspace-hint, [class*="hint"]')?.textContent?.trim() || ''
        }
    }''')
    print(f'  URL: {state["url"]}')
    print(f'  selectStates: {state["selectStates"]}')
    print(f'  tabs: {state["tabs"]}')
    print(f'  hint: {state["hintText"]}')

    # 切到领域 tab
    print('\n=== Step 5: 切到领域 tab ===')
    if state['tabs']:
        cli.evaluate('''() => {
            for (const t of document.querySelectorAll('.el-tabs__item')) {
                if (t.textContent.includes('领域')) { t.click(); return }
            }
        }''')
        cli.wait_for_stable(2000)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/simple_domain_tab.png')

    # 找"新建"按钮
    print('\n=== Step 6: 找"新建"按钮 ===')
    new_btn = cli.evaluate('''() => {
        for (const b of document.querySelectorAll('button')) {
            const t = b.textContent.trim()
            if (t === '新建' || t === '+ 新建' || t.includes('新建')) {
                return { text: t, class: b.className.substring(0, 100) }
            }
        }
        return null
    }''')
    print(f'  新建按钮: {new_btn}')

    if new_btn:
        cli.evaluate('''() => {
            for (const b of document.querySelectorAll('button')) {
                const t = b.textContent.trim()
                if (t === '新建' || t === '+ 新建' || t.includes('新建')) { b.click(); return }
            }
        }''')
        cli.wait_for_stable(3500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/simple_new_clicked.png')

        # 看 form 状态
        print('\n=== Step 7: 检查新建表单 ===')
        new_state = cli.evaluate('''() => {
            return {
                url: window.location.href,
                formItems: Array.from(document.querySelectorAll('.el-form-item')).map(item => {
                    const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                    const input = item.querySelector('input')
                    const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                    return { label, value: input?.value || selectVal || '' }
                })
            }
        }''')
        print(f'  URL: {new_state["url"]}')
        print(f'  字段:')
        for f in new_state['formItems']:
            print(f'    {f}')

        # 单独看 version 字段
        version_field = [f for f in new_state['formItems'] if '版本' in f['label'] or 'version' in f['label'].lower()]
        print(f'\n  ★ version 字段: {version_field}')

    print('\n=== Done ===')
