"""
直接读 useValueHelp 内部 optionsList 验证 intersection
"""
import sys
import time

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    cli = PlaywrightCLI()
    page = None
    try:
        page = cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-tabs, .multi-object-management', timeout=20000)
        time.sleep(3.0)
        page.evaluate("() => { for (const k of Object.keys(localStorage)) if (k.startsWith('recent_')) localStorage.removeItem(k) }")

        selects = page.query_selector_all(".el-select__wrapper")
        selects[0].click(force=True); time.sleep(1.5)
        opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
        opts[0].click(force=True) if opts else None
        time.sleep(2.0)
        selects = page.query_selector_all(".el-select__wrapper")
        selects[1].click(force=True); time.sleep(1.5)
        opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
        opts[0].click(force=True) if opts else None
        time.sleep(2.0)

        page.query_selector(".el-tabs__item:has-text('业务对象')").click()
        time.sleep(2.0)
        page.query_selector("button:has-text('新建')").click()
        time.sleep(4.0)

        # 选领域
        pos = page.evaluate("""() => {
            const drawer = document.querySelector('.el-drawer')
            const items = drawer.querySelectorAll('.el-form-item, .op-field')
            for (const item of items) {
                const labelEl = item.querySelector('.el-form-item__label, .field-label, label, .op-label')
                if (!labelEl) continue
                if (!labelEl.textContent.trim().includes('领域')) continue
                const sel = item.querySelector('.el-select__wrapper')
                if (sel) {
                    const rect = sel.getBoundingClientRect()
                    return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 }
                }
            }
            return null
        }""")
        if pos:
            page.mouse.click(pos['x'], pos['y']); time.sleep(1.5)
            opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
            opts[0].click(force=True) if opts else None
            time.sleep(2.5)
            print("[1] 选领域完成")

        # 注入 fake recent 项
        page.evaluate("""() => {
            const targetKey = 'recent_value_help_sub_domain'
            localStorage.setItem(targetKey, JSON.stringify([
                { value: 999999, display: 'FAKE_子领域_999999', code: 'FAKE_999999' },
                { value: 999998, display: 'FAKE_子领域_999998', code: 'FAKE_999998' },
            ]))
        }""")
        print("[2] 注入 fake recent items")

        # 触发子领域 loadOptions：通过点开 dropdown
        pos = page.evaluate("""() => {
            const drawer = document.querySelector('.el-drawer')
            const items = drawer.querySelectorAll('.el-form-item, .op-field')
            for (const item of items) {
                const labelEl = item.querySelector('.el-form-item__label, .field-label, label, .op-label')
                if (!labelEl) continue
                if (!labelEl.textContent.trim().includes('子领域')) continue
                const sel = item.querySelector('.el-select__wrapper')
                if (sel) {
                    const rect = sel.getBoundingClientRect()
                    return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 }
                }
            }
            return null
        }""")
        if not pos:
            print("[FAIL] 找不到子领域字段")
            return False
        page.mouse.click(pos['x'], pos['y'])
        time.sleep(3.0)  # 等后端返回

        # 直接读 ValueHelpField 的 setupState.optionsList
        result = page.evaluate("""() => {
            const drawer = document.querySelector('.el-drawer')
            const allSelects = drawer.querySelectorAll('.el-select')
            for (const s of allSelects) {
                const labelEl = s.closest('.op-field, .el-form-item')?.querySelector('label, .op-label, .el-form-item__label')
                if (!labelEl) continue
                if (!labelEl.textContent.includes('子领域')) continue
                let v = s.__vueParentComponent
                for (let i = 0; i < 20 && v; i++) {
                    if (v.setupState?.optionsList !== undefined) {
                        const list = v.setupState.optionsList?.value || v.setupState.optionsList || []
                        const bs = v.setupState.bindingSatisfied
                        return {
                            foundAt: i,
                            optionsListLength: Array.isArray(list) ? list.length : 'not array',
                            bindingSatisfied: bs?.value ?? bs,
                            loading: v.setupState.loading?.value ?? v.setupState.loading,
                            formValues: v.setupState.props?.formValues ? Object.fromEntries(Object.entries(v.setupState.props.formValues).slice(0, 5)) : null,
                            sourceId: v.setupState.sourceId?.value ?? v.setupState.sourceId,
                            sourceType: v.setupState.sourceType?.value ?? v.setupState.sourceType,
                            recentKey: v.setupState.recentKey?.value ?? v.setupState.recentKey,
                            localStorageKey: v.setupState.recentKey ? localStorage.getItem(v.setupState.recentKey.value) : null,
                            fakeInList: list.some(o => String(o.value) === '999999' || String(o.value) === '999998'),
                            items: list.slice(0, 8).map(o => ({
                                value: o.value,
                                display: o.display || o.label,
                                isRecent: o.isRecent || false
                            }))
                        }
                    }
                    v = v.parent
                }
                return { error: 'no parent with optionsList' }
            }
            return { error: 'no sub_domain select' }
        }""")
        print(f"\n[3] ValueHelpField.optionsList:")
        print(f"    total: {result.get('optionsListLength')}")
        print(f"    contains FAKE: {result.get('fakeInList')}")
        if result.get('items'):
            for it in result['items']:
                marker = "★" if it.get('isRecent') else " "
                print(f"    {marker} value={it['value']} display='{it['display']}'")

        if result.get('fakeInList'):
            print("\n[FAIL] 修复未生效：FAKE 项仍在 optionsList 里")
            return False
        else:
            print("\n[OK] 修复生效：FAKE 项已被 intersection 过滤")
            return True
    except Exception as e:
        import traceback; traceback.print_exc()
        return False
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
