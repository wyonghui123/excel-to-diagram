"""
直接 inject fake recent 项到 localStorage 验证 intersection 修复
"""
import sys
import time
import json

sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    cli = PlaywrightCLI()
    page = None
    try:
        page = cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-tabs, .multi-object-management', timeout=20000)
        time.sleep(3.0)

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
            page.mouse.click(pos['x'], pos['y'])
            time.sleep(1.5)
            opts = [o for o in page.query_selector_all(".el-select-dropdown__item") if o.is_visible()]
            opts[0].click(force=True) if opts else None
            time.sleep(2.0)
            print("[1] 选领域完成")

        # 找到子领域 select 的源 ID：先看后端会用什么 key
        # 注入 fake recent 项到一个不存在的子领域 id（比如 999999）
        # 然后打开子领域 dropdown，看下拉内容
        # 关键断言：fake 项 value=999999 不应出现在下拉里
        time.sleep(0.5)

        # 注入 fake recent items（含一个 fake id=999999 不存在的子领域 + 几个真实 id）
        inject_result = page.evaluate("""() => {
            // 先查后端用的 key（看 localStorage 里现有的 key 名）
            const existingKeys = Object.keys(localStorage).filter(k => k.startsWith('recent_value_help'))
            // 用现有的 key 名注入 fake
            const targetKey = existingKeys.find(k => k.includes('sub_domain')) || 'recent_value_help_sub_domain'
            const fakeItems = [
                { value: 999999, display: 'FAKE_OLD_子领域_999999', code: 'FAKE_999999' },
                { value: 999998, display: 'FAKE_OLD_子领域_999998', code: 'FAKE_999998' },
            ]
            localStorage.setItem(targetKey, JSON.stringify(fakeItems))
            return { existingKeys, targetKey, injected: fakeItems }
        }""")
        print(f"[2] 注入 fake recent: {inject_result}")

        # 点开子领域 dropdown
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
        time.sleep(3.0)  # 等下拉加载

        # 读下拉内容
        items = page.evaluate("""() => {
            const out = []
            for (const el of document.querySelectorAll('.el-select-dropdown__item')) {
                const rect = el.getBoundingClientRect()
                if (rect.width === 0 || rect.height === 0) continue
                out.push({
                    text: el.textContent.trim(),
                    isFake: el.textContent.includes('FAKE')
                })
            }
            return out
        }""")
        print(f"[3] 子领域下拉内容（{len(items)} 项）:")
        for it in items:
            marker = "⚠" if it.get('isFake') else " "
            print(f"    {marker} {it['text']}")

        fake_count = sum(1 for it in items if it.get('isFake'))
        print(f"\n[RESULT] 下拉中含 FAKE（应被过滤）: {fake_count} 项")
        if fake_count == 0:
            print("[OK] 修复生效！FAKE 项已被 intersection 过滤")
            return True
        else:
            print("[FAIL] 修复未生效，FAKE 项仍出现在下拉")
            return False
    except Exception as e:
        import traceback; traceback.print_exc()
        return False
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
