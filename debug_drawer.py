"""
实际复现：架构数据管理 - 选 product+version - 切到领域 tab - 点新建
看 drawer/form 哪里
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
    print('  [OK]')

    # 选版本
    print('\n=== Step 3: 选版本 ===')
    cli.evaluate('''() => {
        document.querySelectorAll('.el-select')[1].querySelector('.el-select__wrapper').click()
    }''')
    cli.wait_for_stable(1500)
    cli.evaluate('''() => {
        for (const d of document.querySelectorAll('.el-select-dropdown')) {
            if (d.checkVisibility && d.checkVisibility()) {
                const items = d.querySelectorAll('.el-select-dropdown__item')
                if (items[0]) { items[0].click(); return }
            }
        }
    }''')
    cli.wait_for_stable(2500)
    print('  [OK]')

    # 切到 领域 tab
    print('\n=== Step 4: 切到 领域 tab ===')
    cli.evaluate('''() => {
        // 找所有 el-tabs__nav 下的 tab
        const items = document.querySelectorAll('.el-tabs__item, [class*="tab-item"], [role="tab"]')
        for (const t of items) {
            if (t.textContent.trim() === '领域' || t.textContent.includes('领域')) {
                t.click()
                return t.textContent.trim()
            }
        }
        return 'not found'
    }''')
    cli.wait_for_stable(2500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/drawer_step4_domain.png')

    # 看 page state
    state = cli.evaluate('''() => {
        return {
            url: window.location.href,
            tabs: Array.from(document.querySelectorAll('.el-tabs__item, [class*="tab-item"]')).map(t => ({
                text: t.textContent.trim(),
                active: t.classList.contains('is-active')
            })),
        }
    }''')
    print(f'  URL: {state["url"]}')
    print(f'  tabs: {state["tabs"]}')

    # 找"新建"按钮 - 必须在领域 tab 可见
    print('\n=== Step 5: 找"新建"按钮（领域 tab）===')
    btn = cli.evaluate('''() => {
        // 找所有 visible 按钮，找 "新建" 文本
        const buttons = document.querySelectorAll('button')
        for (const b of buttons) {
            const text = b.textContent.trim()
            if (text === '新建' || text === '+ 新建' || (text.includes('新建') && text.length < 20)) {
                const rect = b.getBoundingClientRect()
                if (rect.width > 0 && rect.height > 0) {
                    return { text, class: b.className.substring(0, 100), visible: true }
                }
            }
        }
        return null
    }''')
    print(f'  新建按钮: {btn}')

    if btn:
        # 触发之前先看 drawer 状态
        print('\n=== Step 6: 触发前看 drawer/form 状态 ===')
        before = cli.evaluate('''() => {
            return {
                drawerCount: document.querySelectorAll('.el-drawer, .el-dialog, [class*="drawer"], [class*="dialog"]').length,
                openDrawers: Array.from(document.querySelectorAll('.el-drawer, .el-dialog')).filter(d => {
                    return d.style.display !== 'none' && getComputedStyle(d).display !== 'none'
                }).length,
            }
        }''')
        print(f'  前: {before}')

        # 点击
        cli.evaluate('''() => {
            for (const b of document.querySelectorAll('button')) {
                const text = b.textContent.trim()
                if (text === '新建' || text === '+ 新建' || (text.includes('新建') && text.length < 20)) {
                    const rect = b.getBoundingClientRect()
                    if (rect.width > 0 && rect.height > 0) { b.click(); return }
                }
            }
        }''')
        cli.wait_for_stable(3500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/drawer_step6_after_click.png')

        after = cli.evaluate('''() => {
            const drawer = document.querySelector('.el-drawer')
            const dialog = document.querySelector('.el-dialog')
            return {
                url: window.location.href,
                drawerCount: document.querySelectorAll('.el-drawer, .el-dialog').length,
                drawerVisible: drawer ? getComputedStyle(drawer).display !== 'none' : false,
                dialogVisible: dialog ? getComputedStyle(dialog).display !== 'none' : false,
                allForms: document.querySelectorAll('form, .el-form, .object-detail-page, [class*="form"]').length,
                formItems: Array.from(document.querySelectorAll('.el-form-item')).map(item => {
                    const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                    const input = item.querySelector('input')
                    const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                    return { label, value: input?.value || selectVal || '' }
                })
            }
        }''')
        print(f'  后: {after}')

    print('\n=== Done ===')
