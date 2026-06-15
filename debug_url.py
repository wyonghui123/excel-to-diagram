"""
用 URL 参数方式直接测 /detail/domain?mode=add&productId=19&versionId=14
跳过 UI select 事件触发的复杂性
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    # 先用一个产品+版本（TEST15 = id 19, TEST15_01 = id 14）
    print('=== Step 1: 直接通过 URL 传 productId+versionId 打开 /detail/domain?mode=add ===')
    cli.authenticated_navigate('/detail/domain?mode=add&productId=19&versionId=14')
    cli.wait_for_stable(5000)
    cli.screenshot('d:/filework\excel-to-diagram/test_output/url_detail.png')

    # 看 URL 和 form 状态
    state = cli.evaluate('''() => {
        return {
            url: window.location.href,
            formItems: Array.from(document.querySelectorAll('.el-form-item')).map(item => {
                const label = item.querySelector('.el-form-item__label')?.textContent?.trim() || ''
                const input = item.querySelector('input')
                const selectVal = item.querySelector('.el-select__wrapper')?.textContent?.trim()
                return { label, value: input?.value || selectVal || '' }
            }),
            selectStates: Array.from(document.querySelectorAll('.el-select')).map(s => ({
                placeholder: s.querySelector('.el-select__placeholder')?.textContent?.trim() || '',
                wrap: s.querySelector('.el-select__wrapper')?.textContent?.trim() || '',
                isDisabled: s.classList.contains('is-disabled')
            }))
        }
    }''')
    print(f'  URL: {state["url"]}')
    print(f'  formItems:')
    for f in state['formItems']:
        print(f'    {f}')
    print(f'  selectStates:')
    for s in state['selectStates']:
        print(f'    {s}')

    # 看 DetailPage 的 data
    detail_data = cli.evaluate('''() => {
        const app = document.querySelector('#app').__vue_app__
        const root = app._instance
        const visited = new Set()
        let result = { found: false }
        function walk(node, depth = 0) {
            if (!node || visited.has(node) || depth > 30) return
            visited.add(node)
            const name = node.type?.__name || node.type?.name
            if (name === 'DetailPage') {
                const ss = node.setupState
                if (ss) {
                    result = {
                        found: true,
                        name,
                        data: ss.data?.value,
                        mode: ss.effectiveMode?.value,
                        selectedVersionId: ss.selectedVersionId?.value,
                        productId: ss.productId?.value,
                        versionId: ss.versionId?.value,
                        props: { objectType: node.props?.objectType, mode: node.props?.mode }
                    }
                }
            }
            if (node.subTree) walk(node.subTree, depth + 1)
            if (node.children && Array.isArray(node.children)) {
                for (const c of node.children) {
                    if (typeof c === 'object' && c) walk(c, depth + 1)
                }
            }
        }
        walk(root)
        return result
    }''')
    print(f'\n  DetailPage state: {detail_data}')

    # 同时看 version context
    ctx = cli.evaluate('''() => {
        const app = document.querySelector('#app').__vue_app__
        const root = app._instance
        const visited = new Set()
        let result = null
        function walk(node) {
            if (!node || visited.has(node)) return
            visited.add(node)
            if (node.setupState && node.setupState.versionContext) {
                const ctx = node.setupState.versionContext
                result = {
                    productId: ctx.selectedProductId?.value,
                    versionId: ctx.selectedVersionId?.value,
                    versions: ctx.versions?.value?.length
                }
            }
            if (node.subTree) walk(node.subTree)
            if (node.children && Array.isArray(node.children)) {
                for (const c of node.children) {
                    if (typeof c === 'object' && c) walk(c)
                }
            }
        }
        walk(root)
        return result
    }''')
    print(f'  version context: {ctx}')

    print('\n=== Done ===')
