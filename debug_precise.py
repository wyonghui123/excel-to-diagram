"""
精确测试 - 用 Playwright click 而非 JS evaluate, 避免误点
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    print('=== Step 1: 打开架构数据管理 ===')
    cli.authenticated_navigate('/system/archdata')
    cli.wait_for_stable(2500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step1.png')

    # === Step 2: 用精确选择器选产品 ===
    print('\n=== Step 2: 选产品（用 el-select 顺序定位）===')
    # 第一个 el-select 是产品
    # 点击它的 .el-select__wrapper
    cli.evaluate('''() => {
        const selects = document.querySelectorAll('.el-select')
        const productSel = selects[0]
        productSel.querySelector('.el-select__wrapper').click()
    }''')
    cli.wait_for_stable(1500)

    # 等下拉出现
    cli.wait_for_timeout(800)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step2_product_open.png')

    # 选第一个产品 - 通过 visible dropdown 的 items
    cli.evaluate('''() => {
        const dropdowns = document.querySelectorAll('.el-select-dropdown')
        for (const d of dropdowns) {
            if (d.checkVisibility && d.checkVisibility()) {
                const items = d.querySelectorAll('.el-select-dropdown__item')
                console.log('dropdown items count:', items.length)
                if (items[0]) items[0].click()
                return items.length
            }
        }
        return 0
    }''')
    cli.wait_for_stable(2500)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step2_product_selected.png')

    # 验证 product 已选
    state = cli.evaluate('''() => {
        return Array.from(document.querySelectorAll('.el-select')).map((s, i) => {
            const ph = s.querySelector('.el-select__placeholder')?.textContent?.trim() || ''
            const wrap = s.querySelector('.el-select__wrapper')?.textContent?.trim() || ''
            return { idx: i, ph, wrap: wrap.substring(0, 30) }
        })
    }''')
    print(f'  选完产品后:')
    for s in state:
        print(f'    [{s["idx"]}] ph="{s["ph"]}" wrap="{s["wrap"]}"')

    # === Step 3: 等待 fetchVersions 完成 ===
    print('\n=== Step 3: 等待版本列表加载 ===')
    cli.wait_for_timeout(2000)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step3_loaded.png')

    # 检查 versions 是否有数据（通过 globalToolbarRef 暴露的 versions）
    versions = cli.evaluate('''() => {
        // 尝试拿 globalToolbarRef
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) return { error: 'no app' }

        // 找 GlobalToolbar 组件
        const root = app._instance
        let toolbar = null
        function findComponent(node, name) {
            if (!node) return
            if (node.type?.name === name) { toolbar = node; return }
            if (node.subTree) findComponent(node.subTree, name)
            if (node.children) {
                for (const c of node.children) {
                    if (typeof c !== 'object') continue
                    findComponent(c, name)
                    if (toolbar) return
                }
            }
        }
        findComponent(root, 'GlobalToolbar')

        if (!toolbar) return { error: 'no toolbar' }

        // 拿 setup state
        const setupState = toolbar.setupState
        if (!setupState) return { error: 'no setupState' }

        // 找 versionContext
        const ctx = setupState.versionContext
        if (!ctx) return { error: 'no context' }

        return {
            productId: ctx.selectedProductId?.value,
            versionId: ctx.selectedVersionId?.value,
            versions: ctx.versions?.value?.map(v => ({id: v.id, name: v.name, code: v.code})),
            products: ctx.products?.value?.map(p => ({id: p.id, name: p.name}))
        }
    }''')
    print(f'  version context: {versions}')

    # === Step 4: 选版本（如果有版本）===
    print('\n=== Step 4: 选版本 ===')
    if versions and versions.get('versions'):
        # 选第一个版本
        cli.evaluate('''() => {
            const selects = document.querySelectorAll('.el-select')
            const versionSel = selects[1]
            versionSel.querySelector('.el-select__wrapper').click()
        }''')
        cli.wait_for_stable(1500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step4_version_open.png')

        version_dropdown_count = cli.evaluate('''() => {
            const dropdowns = document.querySelectorAll('.el-select-dropdown')
            for (const d of dropdowns) {
                if (d.checkVisibility && d.checkVisibility()) {
                    const items = d.querySelectorAll('.el-select-dropdown__item')
                    if (items[0]) {
                        const first = items[0]
                        const text = first.textContent.trim()
                        first.click()
                        return { count: items.length, first: text }
                    }
                }
            }
            return { count: 0 }
        }''')
        print(f'  版本下拉选项: {version_dropdown_count}')
        cli.wait_for_stable(2500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step4_version_selected.png')

        # 验证
        versions2 = cli.evaluate('''() => {
            const app = document.querySelector('#app')?.__vue_app__
            const root = app._instance
            let toolbar = null
            function findComponent(node, name) {
                if (!node) return
                if (node.type?.name === name) { toolbar = node; return }
                if (node.subTree) findComponent(node.subTree, name)
                if (node.children) {
                    for (const c of node.children) {
                        if (typeof c !== 'object') continue
                        findComponent(c, name)
                        if (toolbar) return
                    }
                }
            }
            findComponent(root, 'GlobalToolbar')
            if (!toolbar) return { error: 'no toolbar' }
            const setupState = toolbar.setupState
            const ctx = setupState.versionContext
            if (!ctx) return { error: 'no context' }
            return {
                productId: ctx.selectedProductId?.value,
                versionId: ctx.selectedVersionId?.value,
                versions: ctx.versions?.value?.map(v => ({id: v.id, name: v.name}))
            }
        }''')
        print(f'  选完版本: {versions2}')

    # === Step 5: 看页面 tabs 状态 ===
    print('\n=== Step 5: 检查 tabs 状态 ===')
    page_state = cli.evaluate('''() => {
        const state = {
            url: window.location.href,
            tabs: [],
            text: document.body.innerText.substring(0, 500)
        }
        document.querySelectorAll('.el-tabs__item, [role="tab"]').forEach(t => {
            state.tabs.push(t.textContent.trim().substring(0, 30))
        })
        return state
    }''')
    print(f'  URL: {page_state["url"]}')
    print(f'  tabs: {page_state["tabs"]}')
    print(f'  页面文本:\n{page_state["text"]}')

    # === Step 6: 切到领域 tab ===
    print('\n=== Step 6: 切到领域 tab ===')
    if page_state['tabs']:
        result = cli.evaluate('''() => {
            const tabs = document.querySelectorAll('.el-tabs__item')
            for (const t of tabs) {
                if (t.textContent.includes('领域') || t.textContent.toLowerCase().includes('domain')) {
                    t.click()
                    return t.textContent.trim()
                }
            }
            return 'not found'
        }''')
        print(f'  切到: {result}')
        cli.wait_for_stable(2000)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step6_domain_tab.png')

    # === Step 7: 找"新建"按钮 ===
    print('\n=== Step 7: 找"新建"按钮 ===')
    new_btn = cli.evaluate('''() => {
        const buttons = document.querySelectorAll('button')
        for (const b of buttons) {
            const text = b.textContent.trim()
            if (text === '新建' || text === '+ 新建' || (text.includes('新建') && !text.includes('架构数据'))) {
                const rect = b.getBoundingClientRect()
                return { text, visible: rect.width > 0 && rect.height > 0, class: b.className.substring(0, 100) }
            }
        }
        return null
    }''')
    print(f'  新建按钮: {new_btn}')

    if new_btn:
        cli.evaluate('''() => {
            const buttons = document.querySelectorAll('button')
            for (const b of buttons) {
                const text = b.textContent.trim()
                if (text === '新建' || text === '+ 新建' || (text.includes('新建') && !text.includes('架构数据'))) {
                    b.click()
                    return true
                }
            }
            return false
        }''')
        cli.wait_for_stable(3500)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/precise_step7_new_clicked.png')

        # === Step 8: 检查 form 的 version 字段 ===
        print('\n=== Step 8: 检查新建表单的 version 字段 ===')
        new_state = cli.evaluate('''() => {
            return {
                url: window.location.href,
                hasForm: !!document.querySelector('.el-form, [class*="detail-page"]'),
                formItems: []
            }
        }''')
        print(f'  URL: {new_state["url"]}')
        print(f'  hasForm: {new_state["hasForm"]}')

        version_field = cli.evaluate('''() => {
            const items = document.querySelectorAll('.el-form-item')
            for (const item of items) {
                const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                if (label.includes('版本') || label === 'version_id' || label === 'version') {
                    const input = item.querySelector('input')
                    const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                    const placeholder = item.querySelector('.el-select__placeholder')?.textContent?.trim()
                    return {
                        label,
                        inputValue: input?.value,
                        selectValue: selectVal,
                        placeholder,
                    }
                }
            }
            return { found: false }
        }''')
        print(f'  version 字段: {version_field}')

        # 看 DetailPage 的 data 状态
        detail_data = cli.evaluate('''() => {
            const app = document.querySelector('#app')?.__vue_app__
            const root = app._instance
            let detail = null
            function find(node, name) {
                if (!node) return
                if (node.type?.__name === name || node.type?.name === name) { detail = node; return }
                if (node.subTree) find(node.subTree, name)
                if (node.children) {
                    for (const c of (Array.isArray(node.children) ? node.children : [node.children])) {
                        if (typeof c !== 'object' || !c) continue
                        find(c, name)
                        if (detail) return
                    }
                }
            }
            find(root, 'DetailPage')
            if (!detail) return { error: 'no DetailPage' }
            return {
                data: detail.setupState?.data?.value,
                mode: detail.setupState?.mode?.value,
                props: { objectType: detail.props?.objectType, mode: detail.props?.mode }
            }
        }''')
        print(f'  DetailPage data: {detail_data}')

    print('\n=== Done ===')
