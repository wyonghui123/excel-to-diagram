"""
直接导航到 /detail/domain?mode=add，看 version 字段
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    print('=== Step 1: 打开架构数据管理（先选 product+version 写入 context）===')
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
    print('  [OK] 选完版本')

    # 验证 context 状态
    ctx_state = cli.evaluate('''() => {
        // 找 global toolbar 的 setup state
        const app = document.querySelector('#app').__vue_app__
        const root = app._instance
        const visited = new Set()
        const result = { productId: null, versionId: null, versionLabel: null }
        function walk(node) {
            if (!node || visited.has(node)) return
            visited.add(node)
            if (node.setupState && node.setupState.versionContext) {
                const ctx = node.setupState.versionContext
                result.productId = ctx.selectedProductId?.value
                result.versionId = ctx.selectedVersionId?.value
                const v = ctx.selectedVersion?.value
                result.versionLabel = v ? v.name : null
            }
            if (node.subTree) walk(node.subTree)
            if (node.children && Array.isArray(node.children)) {
                for (const c of node.children) {
                    if (typeof c === 'object') walk(c)
                }
            }
        }
        walk(root)
        return result
    }''')
    print(f'  context 状态: {ctx_state}')

    # === 关键：直接导航到 /detail/domain?mode=add ===
    print('\n=== Step 4: 导航到 /detail/domain?mode=add ===')
    cli.evaluate('''() => {
        // 用 router.push
        const app = document.querySelector('#app').__vue_app__
        const router = app.config.globalProperties.$router
        router.push('/detail/domain?mode=add')
    }''')
    cli.wait_for_stable(4000)
    cli.screenshot('d:/filework/excel-to-diagram/test_output/direct_detail.png')

    new_url = cli.evaluate('''() => window.location.href''')
    print(f'  跳转后 URL: {new_url}')

    # 看 form 状态
    print('\n=== Step 5: 检查 form 字段 ===')
    form_state = cli.evaluate('''() => {
        return {
            formItems: Array.from(document.querySelectorAll('.el-form-item')).map(item => {
                const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                const input = item.querySelector('input')
                const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                return { label, value: input?.value || selectVal || '' }
            })
        }
    }''')
    print(f'  formItems:')
    for f in form_state['formItems']:
        print(f'    {f}')

    # 看 DetailPage 组件的 data
    detail_data = cli.evaluate('''() => {
        const app = document.querySelector('#app').__vue_app__
        const root = app._instance
        const visited = new Set()
        let result = { found: false }
        function walk(node) {
            if (!node || visited.has(node)) return
            visited.add(node)
            const name = node.type?.__name || node.type?.name
            if (name === 'DetailPage' || name === 'ObjectDetailPage') {
                const ss = node.setupState
                if (ss) {
                    result = {
                        found: true,
                        name,
                        data: ss.data?.value,
                        mode: ss.effectiveMode?.value || ss.mode?.value,
                        props: {
                            objectType: node.props?.objectType,
                            mode: node.props?.mode,
                            id: node.props?.id
                        }
                    }
                }
            }
            if (node.subTree) walk(node.subTree)
            if (node.children && Array.isArray(node.children)) {
                for (const c of node.children) {
                    if (typeof c === 'object') walk(c)
                }
            }
        }
        walk(root)
        return result
    }''')
    print(f'\n  DetailPage state: {detail_data}')

    print('\n=== Done ===')
