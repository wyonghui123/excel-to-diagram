"""
UI 验证测试：新建子领域时，版本字段是否正确显示选中版本

验证流程：
1. 登录 + 选产品 + 选版本
2. 切到"子领域" tab
3. 点"新建"按钮
4. 检查版本字段在新建表单中是否正确显示（不为空、不显示 placeholder）
5. 检查所有字段
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI

OUT_DIR = Path("d:/filework/excel-to-diagram/test_output/ui_subdomain")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    cli = PlaywrightCLI()
    page = None
    try:
        # Step 1: 登录
        print("[1] 登录...")
        page = cli.authenticated_navigate(
            '/system/archdata',
            wait_for_selector='.el-tabs, .multi-object-management',
            timeout=20000
        )
        time.sleep(3.0)

        # Step 2: 选产品
        print("[2] 选产品+版本...")
        selects = page.query_selector_all(".el-select__wrapper")
        if not selects or len(selects) < 1:
            print("    [FAIL] 找不到产品 select")
            return False

        # 选第一个产品
        selects[0].click(force=True)
        time.sleep(1.5)
        options = page.query_selector_all(".el-select-dropdown__item")
        visible = [o for o in options if o.is_visible()]
        if not visible:
            print("    [FAIL] 产品下拉没选项")
            return False
        product_name = visible[0].text_content().strip()
        visible[0].click(force=True)
        time.sleep(2.0)
        print(f"    选中的产品: {product_name}")

        # 选版本
        time.sleep(1.0)
        selects = page.query_selector_all(".el-select__wrapper")
        if len(selects) < 2:
            print("    [FAIL] 找不到版本 select")
            return False
        selects[1].click(force=True)
        time.sleep(1.5)
        options = page.query_selector_all(".el-select-dropdown__item")
        visible = [o for o in options if o.is_visible()]
        if not visible:
            print("    [FAIL] 版本下拉没选项")
            return False
        version_name = visible[0].text_content().strip()
        visible[0].click(force=True)
        time.sleep(2.0)
        print(f"    选中的版本: {version_name}")

        # 记录选中的版本id (从内部 store)
        selected_version_id = page.evaluate("""() => {
            const app = document.querySelector('#app')?.__vue_app__
            const pinia = app?.config?.globalProperties?.$pinia
            if (!pinia) return null
            for (const [key, store] of pinia._s) {
                if (store.selectedVersionId !== undefined) {
                    return store.selectedVersionId
                }
                if (store.version_id !== undefined) {
                    return store.version_id
                }
            }
            return null
        }""")
        print(f"    选中的 version_id: {selected_version_id}")

        # Step 3: 切到子领域 tab
        print("[3] 切到'子领域' tab...")
        subdomain_tab = page.query_selector(".el-tabs__item:has-text('子领域')")
        if not subdomain_tab:
            print("    [FAIL] 找不到'子领域' tab")
            return False
        subdomain_tab.click()
        time.sleep(2.5)
        page.screenshot(path=str(OUT_DIR / "01_subdomain_tab.png"))

        # Step 4: 点"新建"按钮
        print("[4] 点'新建'按钮...")
        new_btn = page.query_selector("button:has-text('新建')")
        if not new_btn:
            print("    [FAIL] 找不到'新建'按钮")
            return False
        new_btn.click()
        time.sleep(4.0)
        page.screenshot(path=str(OUT_DIR / "02_new_drawer.png"))

        # Step 5: 检查版本字段
        print("[5] 检查版本字段显示...")
        version_check = page.evaluate("""() => {
            const drawer = document.querySelector('.el-drawer')
            if (!drawer) return { error: 'no drawer' }

            // 找 DetailPage 组件
            let el = drawer
            while (el && !el.__vueParentComponent) el = el.parentElement
            if (!el || !el.__vueParentComponent) return { error: 'no vue parent' }

            let vnode = el.__vueParentComponent
            let dataVal = null
            let selectedVersionIdVal = null
            for (let i = 0; i < 20 && vnode; i++) {
                if (vnode.setupState?.data) {
                    const setup = vnode.setupState
                    dataVal = setup.data?.value || setup.data
                    selectedVersionIdVal = setup.selectedVersionId?.value ?? setup.selectedVersionId
                    break
                }
                vnode = vnode.parent
            }

            // 找所有"版本"字段
            const items = drawer.querySelectorAll('.el-form-item, .form-field, .op-field')
            const versionInfo = {
                found: false,
                dataVal: dataVal ? { ...dataVal } : null,
                selectedVersionId: selectedVersionIdVal
            }

            for (const item of items) {
                const labelEl = item.querySelector('.el-form-item__label, .field-label, label, .op-label')
                if (!labelEl) continue
                const label = labelEl.textContent.trim()

                if (label.includes('版本') || label.toLowerCase().includes('version')) {
                    const sel = item.querySelector('.el-select__wrapper')
                    if (sel) {
                        const selection = sel.querySelector('.el-select__selection')
                        const placeholder = sel.querySelector('.el-select__placeholder')
                        const isDisabled = sel.classList.contains('is-disabled')

                        const selectionText = selection?.textContent?.trim() || ''
                        const placeholderText = placeholder?.textContent?.trim() || ''
                        const placeholderHidden = placeholder && placeholder.classList.contains('is-hidden')

                        versionInfo.found = true
                        versionInfo.label = label
                        versionInfo.selectionText = selectionText
                        versionInfo.placeholderText = placeholderText
                        versionInfo.placeholderHidden = placeholderHidden
                        versionInfo.isDisabled = isDisabled
                        versionInfo.isDisplaying = (
                            selectionText.length > 0 &&
                            (placeholderHidden || selectionText !== placeholderText)
                        )
                    } else {
                        versionInfo.found = true
                        versionInfo.label = label
                        versionInfo.widget = 'no-select'
                    }
                }
            }
            return versionInfo
        }""")
        print(f"    版本字段检查结果:")
        for k, v in version_check.items():
            if k == 'dataVal' and v:
                print(f"        {k}: {v}")
            else:
                print(f"        {k}: {v}")

        # Step 6: 检查所有字段
        print("[6] 检查所有字段...")
        all_fields = page.evaluate("""() => {
            const drawer = document.querySelector('.el-drawer')
            if (!drawer) return []

            const opFields = drawer.querySelectorAll('.op-field, .value-help-field, .el-form-item')
            const fields = []

            for (const item of opFields) {
                const labelEl = item.querySelector('.op-field > label, .el-form-item__label, .field-label, label, .op-label')
                const label = labelEl ? labelEl.textContent.trim() : '?'

                const sel = item.querySelector('.el-select__wrapper')
                const inputs = item.querySelectorAll('input[type="text"]:not([readonly])')
                const allInputs = item.querySelectorAll('input')

                if (sel) {
                    const selection = sel.querySelector('.el-select__selection')
                    const placeholder = sel.querySelector('.el-select__placeholder')
                    const isDisabled = sel.classList.contains('is-disabled')
                    const selectionText = selection?.textContent?.trim() || ''
                    const placeholderText = placeholder?.textContent?.trim() || ''
                    const placeholderHidden = placeholder && placeholder.classList.contains('is-hidden')
                    const hasValue = selectionText.length > 0 && (placeholderHidden || selectionText !== placeholderText)
                    fields.push({
                        label,
                        type: 'select',
                        value: selectionText,
                        placeholder: placeholderText,
                        isDisabled,
                        hasValue
                    })
                } else if (inputs.length > 0 || allInputs.length > 0) {
                    const inp = inputs[0] || allInputs[0]
                    fields.push({
                        label,
                        type: 'input',
                        value: inp.value || '',
                        placeholder: inp.placeholder || '',
                        hasValue: !!(inp.value && inp.value !== inp.placeholder)
                    })
                }
            }
            return fields
        }""")
        for f in all_fields:
            mark = '[OK]' if f.get('hasValue') else '[ ]'
            extra = f' disabled={f.get("isDisabled")}' if 'isDisabled' in f else ''
            print(f"    {mark} label='{f['label']}' type={f['type']} value='{f.get('value','')}' placeholder='{f.get('placeholder','')}'{extra}")

        # Step 7: 关键判断
        print("\n" + "="*60)
        # selectionText 非空且不等于 '请选择' 就算显示（placeholder 文本可能是空或不固定）
        sel_text = (version_check.get('selectionText') or '').strip()
        sel_is_displaying = (
            version_check.get('found') and
            sel_text and
            sel_text != '请选择'
        )
        if sel_is_displaying:
            print(f"[OK] 版本字段已正确显示: '{sel_text}'")
            return True
        else:
            print(f"[BUG] 版本字段未正确显示!")
            print(f"      found={version_check.get('found')}")
            print(f"      selectionText='{version_check.get('selectionText','')}'")
            print(f"      placeholderText='{version_check.get('placeholderText','')}'")
            print(f"      isDisabled={version_check.get('isDisabled')}")
            print(f"      selectedVersionId (from store)={version_check.get('selectedVersionId')}")

            # 调试 ValueHelpField 内部状态
            print("\n[debug] 检查 ValueHelpField 内部状态...")
            vh_state = page.evaluate("""() => {
                const drawer = document.querySelector('.el-drawer')
                if (!drawer) return { error: 'no drawer' }

                let el = drawer
                while (el && !el.__vueParentComponent) el = el.parentElement
                if (!el) return { error: 'no vue' }

                let vnode = el.__vueParentComponent
                for (let i = 0; i < 30 && vnode; i++) {
                    if (vnode.type?.name === 'ValueHelpField') {
                        const setup = vnode.setupState
                        const props = setup.props || {}
                        return {
                            found: true,
                            modelValue: props.modelValue,
                            internalValue: setup.internalValue?.value ?? setup.internalValue,
                            optionsListLength: setup.optionsList?.value?.length,
                            optionsListFirst5: (setup.optionsList?.value || []).slice(0, 5).map(o => ({
                                value: o.value,
                                display: o.display || o.label
                            })),
                            loading: setup.loading?.value ?? setup.loading,
                            disabled: props.disabled,
                            readonly: props.readonly,
                            isMultiple: setup.isMultiple?.value ?? setup.isMultiple
                        }
                    }
                    vnode = vnode.parent
                }
                return { error: 'ValueHelpField not found in DOM tree' }
            }""")
            print(f"    ValueHelpField state: {vh_state}")

            # 等 5s 后再检查一次，看 options 加载完成没
            print("\n[debug] 等待 5s，看 options 加载完成情况...")
            time.sleep(5.0)
            vh_state2 = page.evaluate("""() => {
                const drawer = document.querySelector('.el-drawer')
                if (!drawer) return { error: 'no drawer' }
                let el = drawer
                while (el && !el.__vueParentComponent) el = el.parentElement
                if (!el) return { error: 'no vue' }
                let vnode = el.__vueParentComponent
                for (let i = 0; i < 30 && vnode; i++) {
                    if (vnode.type?.name === 'ValueHelpField') {
                        const setup = vnode.setupState
                        const props = setup.props || {}
                        const opts = setup.optionsList?.value || []
                        return {
                            internalValue: setup.internalValue?.value ?? setup.internalValue,
                            optionsListLength: opts.length,
                            hasVersion15: opts.some(o => o.value === 15),
                            hasVersion14: opts.some(o => o.value === 14),
                            optionsList: opts.slice(0, 10).map(o => ({ value: o.value, display: o.display || o.label }))
                        }
                    }
                    vnode = vnode.parent
                }
                return { error: 'not found' }
            }""")
            print(f"    5s后: {vh_state2}")
            page.screenshot(path=str(OUT_DIR / "03_after_5s.png"), full_page=True)
            return False
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        cli.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
