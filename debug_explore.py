"""
探索架构数据管理页面结构
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    print('=== Step 1: 登录并打开架构数据管理 ===')
    cli.authenticated_navigate('/system/archdata')
    cli.wait_for_stable(3000)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/explore_archdata.png')

    # 看 URL 和 页面结构
    info = cli.evaluate('''() => {
        return {
            url: window.location.href,
            title: document.title,
            main: document.querySelector('#app, .app, main')?.tagName || 'no main',
            h1: document.querySelector('h1')?.textContent || '',
            h2: document.querySelector('h2')?.textContent || '',
            bodyClass: document.body.className.substring(0, 80)
        }
    }''')
    print(f'URL: {info["url"]}')
    print(f'标题: {info["title"]}')
    print(f'h1: {info["h1"]}, h2: {info["h2"]}')

    # 看所有 tabs
    tabs = cli.evaluate('''() => {
        const all = document.querySelectorAll('[class*="tab"], [role="tablist"]')
        return Array.from(all).slice(0, 20).map(t => ({
            tag: t.tagName,
            class: t.className.substring(0, 80),
            text: t.textContent.trim().substring(0, 100)
        }))
    }''')
    print(f'\n找到 {len(tabs)} 个 tab 相关元素:')
    for t in tabs[:10]:
        print(f'  {t}')

    # 看 select 数量
    selects = cli.evaluate('''() => {
        const all = document.querySelectorAll('.el-select, .el-tabs__item, button')
        return {
            selects: document.querySelectorAll('.el-select').length,
            tabs: document.querySelectorAll('.el-tabs__item').length,
            buttons: document.querySelectorAll('button').length
        }
    }''')
    print(f'\nel-select: {selects["selects"]}, el-tabs__item: {selects["tabs"]}, button: {selects["buttons"]}')

    # 看页面文本
    text = cli.evaluate('''() => {
        return document.body.innerText.substring(0, 1000)
    }''')
    print(f'\n页面文本（前 1000 字符）:\n{text}')

    # 切到 domain tab
    print('\n=== 尝试切到 domain tab ===')
    cli.evaluate('''() => {
        const tabs = document.querySelectorAll('.el-tabs__item')
        for (const t of tabs) {
            if (t.textContent.includes('领域') || t.textContent.includes('Domain')) {
                console.log('click tab:', t.textContent)
                t.click()
                return t.textContent
            }
        }
        return 'not found'
    }''')
    cli.wait_for_stable(1500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/explore_domain_tab.png')

    # 看 domain tab 下的新建按钮
    buttons = cli.evaluate('''() => {
        const btns = document.querySelectorAll('button')
        return Array.from(btns).map(b => b.textContent.trim()).filter(t => t)
    }''')
    print(f'所有按钮: {buttons[:30]}')
