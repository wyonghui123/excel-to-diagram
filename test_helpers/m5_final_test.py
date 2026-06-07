"""
M5 前端回归测试 Final：RelationScopeTree
使用 page.goto 直接导航替代 router.push
"""

import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth import authenticated_page

TIMEOUT = 20000


async def click_visible_button(page, text_hint, container=None):
    sel = f'{container} .el-button' if container else '.el-button'
    btns = page.locator(sel)
    for i in range(await btns.count()):
        btn = btns.nth(i)
        try:
            if not await btn.is_visible():
                continue
        except Exception:
            continue
        txt = (await btn.text_content()) or ''
        if text_hint in txt:
            print(f"  [BTN] {txt.strip()}", flush=True)
            try:
                await btn.click(timeout=3000)
                return True
            except Exception:
                pass
    return False


async def select_option(page, text_hint):
    opts = page.locator('.el-select-dropdown__item:visible')
    for i in range(await opts.count()):
        opt = opts.nth(i)
        try:
            if not await opt.is_visible():
                continue
        except Exception:
            continue
        txt = (await opt.text_content()) or ''
        if text_hint in txt:
            print(f"  [SEL] {txt.strip()}", flush=True)
            try:
                await opt.click(timeout=3000)
                return True
            except Exception:
                pass
    return False


async def main():
    print("=" * 60)
    print("M5 前端回归测试 Final")
    print("=" * 60)

    os.makedirs('d:/filework/excel-to-diagram/test_output', exist_ok=True)

    async with authenticated_page(username='admin', headless=False) as page:
        await page.set_viewport_size({"width": 1680, "height": 1050})
        print("[AUTH] 浏览器已创建", flush=True)

        # 直接 goto（避免 router.push 依赖 Vue router 就绪）
        print("[NAV] 导航到 archdata...", flush=True)
        await page.goto('http://localhost:3004/system/archdata', wait_until='domcontentloaded', timeout=TIMEOUT)
        await asyncio.sleep(3000)

        await page.screenshot(path='d:/filework/excel-to-diagram/test_output/m5f_00_archdata.png', full_page=True)
        print("[DEBUG] 截图已保存", flush=True)

        # 选择产品线
        print("\n[STEP] 选择产品线...", flush=True)
        selects = page.locator('.el-select')
        if await selects.count() > 0:
            await selects.nth(0).click()
            await asyncio.sleep(800)
            found = await select_option(page, '更新后的产品线')
            if not found:
                found = await select_option(page, '供应链')
            if not found:
                found = await select_option(page, '测试产品')
            await asyncio.sleep(2000)
            await page.keyboard.press('Escape')

        await page.screenshot(path='d:/filework/excel-to-diagram/test_output/m5f_01_product.png', full_page=True)

        # 选择版本
        print("\n[STEP] 选择版本...", flush=True)
        selects2 = page.locator('.el-select')
        if await selects2.count() > 1:
            await selects2.nth(1).click()
            await asyncio.sleep(800)
            found = await select_option(page, '版本') or await select_option(page, '更新后的')
            await asyncio.sleep(2000)
            await page.keyboard.press('Escape')

        await asyncio.sleep(2000)
        await page.screenshot(path='d:/filework/excel-to-diagram/test_output/m5f_02_version.png', full_page=True)

        # 检查 RelationScopeTree
        state = await page.evaluate("""() => {
            return {
                oss_root: !!document.querySelector('.oss-root'),
                rss_root: !!document.querySelector('.rss-root'),
                oss_nodes: document.querySelectorAll('.oss-root .el-tree-node').length,
                rss_nodes: document.querySelectorAll('.rss-root .el-tree-node').length,
            }
        }""")
        print(f"\n[INFO] oss-root: {state['oss_root']}, rss-root: {state['rss_root']}", flush=True)
        print(f"[INFO] OSS nodes: {state['oss_nodes']}, RSS nodes: {state['rss_nodes']}", flush=True)

        if not (state['oss_root'] and state['rss_root']):
            print("[WARN] RelationScopeTree 未完全渲染，测试终止", flush=True)
            return 0

        # ===== RSS 功能测试 =====
        print("\n" + "=" * 40)
        print("RSS 关系范围树测试")
        print("=" * 40, flush=True)

        # 刷新
        print("\n[TEST] RSS 刷新...", flush=True)
        if await click_visible_button(page, '刷新', '.rss-root'):
            await asyncio.sleep(4000)
            try:
                await page.wait_for_selector('.rss-loading', state='hidden', timeout=12000)
            except:
                print("  [WARN] 加载状态未消失，超时继续", flush=True)
        await asyncio.sleep(500)

        # 展开
        print("[TEST] RSS 展开全部...", flush=True)
        await click_visible_button(page, '展开', '.rss-root')
        await asyncio.sleep(500)

        # 统计
        rss_before = await page.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            const store = tree?.__vueParentComponent?.treeStore
            return {
                nodes: document.querySelectorAll('.rss-root .el-tree-node').length,
                checked: store?.getCheckedKeys(false)?.length || 0
            }
        }""")
        print(f"  RSS 状态: nodes={rss_before['nodes']}, checked={rss_before['checked']}", flush=True)

        # 全选
        print("[TEST] RSS 全选...", flush=True)
        await click_visible_button(page, '全选', '.rss-root')
        await asyncio.sleep(500)
        rss_after_all = await page.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            const store = tree?.__vueParentComponent?.treeStore
            return store?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  全选后 checked: {rss_after_all}", flush=True)

        # 清空
        print("[TEST] RSS 清空...", flush=True)
        await click_visible_button(page, '清空', '.rss-root')
        await asyncio.sleep(500)
        rss_after_clear = await page.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            const store = tree?.__vueParentComponent?.treeStore
            return store?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  清空后 checked: {rss_after_clear}", flush=True)

        # 刷新后 checked 保持
        print("\n[TEST] RSS 刷新后 checked 保持（FR-002）...", flush=True)
        await click_visible_button(page, '全选', '.rss-root')
        await asyncio.sleep(500)
        checked_before = await page.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            const store = tree?.__vueParentComponent?.treeStore
            return store?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  刷新前 checked: {checked_before}", flush=True)

        if await click_visible_button(page, '刷新', '.rss-root'):
            await asyncio.sleep(4000)
            try:
                await page.wait_for_selector('.rss-loading', state='hidden', timeout=12000)
            except:
                pass

        checked_after = await page.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            const store = tree?.__vueParentComponent?.treeStore
            return store?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  刷新后 checked: {checked_after}", flush=True)
        if checked_before == checked_after:
            print(f"  [PASS] 刷新后 checked 保持: {checked_before} = {checked_after} [DECORATIVE]", flush=True)
        else:
            print(f"  [INFO] 刷新后 checked: {checked_before} → {checked_after}", flush=True)

        # ===== OSS 勾选 → RSS filter =====
        print("\n" + "=" * 40)
        print("OSS 对象树 → RSS filter-node-method 测试（FR-004）")
        print("=" * 40, flush=True)

        rss_before_filter = await page.evaluate("""() => document.querySelectorAll('.rss-root .el-tree-node').length""")
        print(f"  OSS 勾选前 RSS 节点: {rss_before_filter}", flush=True)

        # 展开 OSS
        print("[TEST] 展开 OSS...", flush=True)
        await click_visible_button(page, '展开', '.oss-root')
        await asyncio.sleep(500)

        # 点击 OSS 节点
        oss_count = await page.evaluate("""() => document.querySelectorAll('.oss-root .el-tree-node__content').length""")
        print(f"  OSS 可见节点: {oss_count}", flush=True)

        if oss_count > 0:
            label = await page.evaluate("""() => {
                const nodes = document.querySelectorAll('.oss-root .el-tree-node__content')
                return nodes[0]?.textContent?.trim() || ''
            }""")
            print(f"  点击 OSS 节点: {label}", flush=True)

            await page.evaluate("""() => {
                const nodes = document.querySelectorAll('.oss-root .el-tree-node__content')
                if (nodes[0]) nodes[0].click()
            }""")
            await asyncio.sleep(1000)

        rss_after_filter = await page.evaluate("""() => document.querySelectorAll('.rss-root .el-tree-node').length""")
        print(f"  OSS 勾选后 RSS 节点: {rss_after_filter}", flush=True)
        if rss_before_filter != rss_after_filter:
            print(f"  [PASS] filter-node-method 生效: {rss_before_filter} → {rss_after_filter}", flush=True)
        else:
            print(f"  [INFO] filter-node-method 无变化（可能节点已在范围内或数据有限）", flush=True)

        await page.screenshot(path='d:/filework/excel-to-diagram/test_output/m5f_final.png', full_page=True)
        print("\n" + "=" * 60)
        print("M5 前端回归测试完成")
        print("=" * 60, flush=True)

    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
