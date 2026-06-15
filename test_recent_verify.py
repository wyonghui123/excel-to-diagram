"""
一次性验证：切领域后子领域下拉不含旧领域的子领域
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

        # 清掉 localStorage 里的 recent items（确保从干净状态开始）
        page.evaluate("() => { for (const k of Object.keys(localStorage)) if (k.startsWith('recent_')) localStorage.removeItem(k) }")
        print("[init] 清空 localStorage recent 项")

        # 选产品+版本
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

        # 切到业务对象 tab → 新建
        page.query_selector(".el-tabs__item:has-text('业务对象')").click()
        time.sleep(2.0)
        page.query_selector("button:has-text('新建')").click()
        time.sleep(4.0)

        # 找领域 select（drawer 内，label='领域'）
        def click_field(label_text):
            return page.evaluate("""(labelText) => {
                const drawer = document.querySelector('.el-drawer')
                if (!drawer) return null
                const items = drawer.querySelectorAll('.el-form-item, .op-field')
                for (const item of items) {
                    const labelEl = item.querySelector('.el-form-item__label, .field-label, label, .op-label')
                    if (!labelEl) continue
                    if (!labelEl.textContent.trim().includes(labelText)) continue
                    const sel = item.querySelector('.el-select__wrapper')
                    if (sel) {
                        const rect = sel.getBoundingClientRect()
                        return { x: rect.x + rect.width/2, y: rect.y + rect.height/2 }
                    }
                }
                return null
            }""", label_text)

        def select_first_option_in_visible_dropdown():
            opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
            if not opts: return None
            text = opts[0].text_content().strip()
            opts[0].click(force=True)
            return text

        # 步骤 1: 选第一个领域
        pos = click_field("领域")
        if pos:
            page.mouse.click(pos['x'], pos['y'])
            time.sleep(1.5)
            domain1 = select_first_option_in_visible_dropdown()
            time.sleep(2.0)
            print(f"[1] 选领域: {domain1}")

        # 步骤 2: 选第一个子领域（让 localStorage 记住）
        pos = click_field("子领域")
        if pos:
            page.mouse.click(pos['x'], pos['y'])
            time.sleep(1.5)
            sd1 = select_first_option_in_visible_dropdown()
            time.sleep(2.0)
            print(f"[2] 选子领域（要记到 localStorage）: {sd1}")

        # 验证 localStorage 有这条
        ls = page.evaluate("() => { const out = {}; for (const k of Object.keys(localStorage)) if (k.startsWith('recent_')) out[k] = localStorage.getItem(k); return out; }")
        print(f"[3] localStorage recent: {ls}")

        # 步骤 4: 关掉 drawer 重新打开（清掉 Vue 状态）
        close = page.query_selector(".el-drawer__close-btn")
        if close:
            close.click()
            time.sleep(1.5)

        # 重新选领域
        page.query_selector(".el-tabs__item:has-text('业务对象')").click()
        time.sleep(1.5)
        page.query_selector("button:has-text('新建')").click()
        time.sleep(4.0)

        # 步骤 5: 选**另一个**领域（第二个）
        pos = click_field("领域")
        if pos:
            page.mouse.click(pos['x'], pos['y'])
            time.sleep(1.5)
            opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
            if len(opts) >= 2:
                domain2 = opts[1].text_content().strip()
                opts[1].click(force=True)
                time.sleep(2.5)
                print(f"[4] 切到另一个领域: {domain2}")
            else:
                print("[4] 只有 1 个领域，跳过此步")
                domain2 = None

        # 步骤 6: 点开子领域下拉，看下拉里有什么
        if domain2:
            pos = click_field("子领域")
            if pos:
                page.mouse.click(pos['x'], pos['y'])
                time.sleep(2.5)
                # 等 options 加载
                page.wait_for_selector(".el-select-dropdown__item", timeout=5000)
                # 拿所有下拉项
                all_items = page.evaluate("""() => {
                    const out = []
                    for (const el of document.querySelectorAll('.el-select-dropdown__item')) {
                        if (!el.is_visible) continue
                        const rect = el.getBoundingClientRect()
                        if (rect.width === 0 || rect.height === 0) continue
                        out.push({
                            text: el.textContent.trim(),
                            isRecent: el.classList.contains('is-recent') || el.querySelector('.is-recent') !== null
                        })
                    }
                    return out
                }""")
                print(f"[5] 子领域下拉内容（{len(all_items)} 项）:")
                for it in all_items:
                    marker = "★" if it.get('isRecent') else " "
                    print(f"    {marker} {it['text']}")

                # 关键断言：旧子领域 sd1 不应出现在新领域的下拉里
                contains_old = any(sd1 in it['text'] for it in all_items)
                print(f"\n[RESULT] 旧子领域 '{sd1}' 仍出现在新领域下拉: {contains_old}")
                if contains_old:
                    print("[FAIL] 修复未生效")
                    return False
                else:
                    print("[OK] 修复生效！旧子领域已被过滤")
                    return True
    except Exception as e:
        import traceback; traceback.print_exc()
        return False
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
