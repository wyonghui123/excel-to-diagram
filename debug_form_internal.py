"""
深入检查 form 内部 - 找 version 字段到底在哪
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    print('=== 打开架构数据管理，选 product+version，切领域 tab，点新建 ===')
    cli.authenticated_navigate('/system/archdata')
    cli.wait_for_stable(2500)

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

    cli.evaluate('''() => {
        for (const t of document.querySelectorAll('.el-tabs__item')) {
            if (t.textContent.includes('领域')) { t.click(); return }
        }
    }''')
    cli.wait_for_stable(2000)

    cli.evaluate('''() => {
        for (const b of document.querySelectorAll('button')) {
            const text = b.textContent.trim()
            if (text === '新建' || text === '+ 新建' || (text.includes('新建') && text.length < 20)) {
                const rect = b.getBoundingClientRect()
                if (rect.width > 0 && rect.height > 0) { b.click(); return }
            }
        }
    }''')
    cli.wait_for_stable(4000)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/form_internal.png')

    # 详细检查 form
    form = cli.evaluate('''() => {
        // 找所有 form 容器
        const drawer = document.querySelector('.el-drawer')
        if (!drawer) return { error: 'no drawer' }

        // 找 form
        const formEl = drawer.querySelector('form, .el-form, .meta-form, .object-form')
        if (!formEl) return { error: 'no form' }

        // 找所有 section
        const sections = Array.from(formEl.querySelectorAll('.meta-form-section, .form-section, .el-form-item, [class*="section"]'))
        const result = {
            formHtml: formEl.outerHTML.substring(0, 500),
            sections: [],
            formItems: []
        }

        // 直接收集所有 form-item
        const items = formEl.querySelectorAll('.el-form-item, .form-field, .meta-field')
        items.forEach((item, i) => {
            const label = item.querySelector('.el-form-item__label, .field-label, label')?.textContent?.trim() || ''
            const input = item.querySelector('input, textarea, select')
            const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
            const allText = item.textContent.trim().substring(0, 200)
            result.formItems.push({
                idx: i,
                label,
                value: input?.value || selectVal || '',
                hasInput: !!input,
                hasSelect: !!item.querySelector('.el-select'),
                text: allText
            })
        })

        return result
    }''')
    print(f'\nForm 分析:')
    if 'error' in form:
        print(f'  Error: {form["error"]}')
    else:
        print(f'  formItems (共 {len(form["formItems"])} 个):')
        for f in form['formItems']:
            print(f'    [{f["idx"]}] label="{f["label"]}" value="{f["value"]}" input={f["hasInput"]} select={f["hasSelect"]}')
            print(f'         text="{f["text"][:100]}"')

    # 看 version context 状态
    print('\n=== version context 状态 ===')
    ctx = cli.evaluate('''() => {
        // 通过 window 上的 vue 拿
        const root = document.getElementById('app')?.__vue_app__?._instance
        if (!root) return { error: 'no root' }
        // BFS
        const visited = new Set()
        const queue = [root]
        const found = []
        while (queue.length) {
            const node = queue.shift()
            if (!node || visited.has(node)) continue
            visited.add(node)
            const name = node.type?.__name || node.type?.name
            if (name === 'MetaListPage' || name === 'ObjectPage' || name === 'DetailPage' || name === 'MetaForm') {
                const ss = node.setupState
                if (ss) {
                    found.push({
                        name,
                        keys: Object.keys(ss).filter(k => k.includes('ersion') || k.includes('roduct') || k.includes('context') || k.includes('selected') || k.includes('data'))
                    })
                }
            }
            if (node.subTree) queue.push(node.subTree)
            if (node.children) {
                if (Array.isArray(node.children)) {
                    for (const c of node.children) if (c && typeof c === 'object') queue.push(c)
                } else if (typeof node.children === 'object') {
                    queue.push(node.children)
                }
            }
        }
        return found
    }''')
    print(f'  Found components: {ctx}')

    print('\n=== Done ===')
