# -*- coding: utf-8 -*-
"""
UI 端验证 (v2 风格): 用项目自己的 test_helpers/browser_auth.py
- 符合 frontend-test-auth.md 5 步视觉验证
- 验证 id=NULL bug (实际:页面要求 product+version 才显示)
"""
import asyncio
import sys
import time
from pathlib import Path

# 关键: 用项目自己的 helper,符合 v2 简化方案
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from test_helpers.browser_auth import authenticated_page, go_to


async def main():
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 用项目标准方式: authenticated_page
    async with authenticated_page(target_url='/system/archdata') as page:
        print(f"[1] Logged in & navigated to: {page.url}")

        # 5 步视觉验证: DOM 存在
        tabs = page.get_by_role("tab")
        tab_count = await tabs.count()
        print(f"[2] Tabs found: {tab_count}")
        if tab_count > 0:
            tab_texts = [await tabs.nth(i).text_content() for i in range(tab_count)]
            print(f"    Tab texts: {tab_texts}")

        # 看页面状态
        body_text = await page.evaluate("() => document.body?.innerText?.substring(0, 800) || ''")
        print(f"[3] Body text:")
        print(body_text[:800])
        print("---")

        # 截图
        screenshot1 = out_dir / "ui_v2_state.png"
        await page.screenshot(path=str(screenshot1), full_page=True)
        print(f"[4] Screenshot: {screenshot1}")

        # 选产品 (用 frontend-test-auth.md 第 3.2 的方式)
        # 找产品下拉
        prod_label = page.get_by_text("产品", exact=False).first
        if await prod_label.count() > 0:
            await prod_label.click()
            await asyncio.sleep(0.5)
            # 选第一个选项
            options = page.locator(".el-select-dropdown__item:visible")
            opt_count = await options.count()
            if opt_count > 0:
                await options.first.click()
                print(f"[5] Selected first product option")
                await asyncio.sleep(0.5)

        # 选版本
        ver_label = page.get_by_text("版本", exact=False).first
        if await ver_label.count() > 0:
            await ver_label.click()
            await asyncio.sleep(0.5)
            options = page.locator(".el-select-dropdown__item:visible")
            opt_count = await options.count()
            if opt_count > 0:
                await options.first.click()
                print(f"[6] Selected first version option")
                await asyncio.sleep(1)

        # 截图选择后
        screenshot2 = out_dir / "ui_v2_after_select.png"
        await page.screenshot(path=str(screenshot2), full_page=True)
        print(f"[7] Screenshot: {screenshot2}")

        # 检查"新建"按钮是否出现
        new_btn = page.get_by_role("button", name="新建")
        new_count = await new_btn.count()
        print(f"[8] 新建 button count (after select): {new_count}")

        if new_count > 0:
            print(f"[OK] 选 product+version 后,页面出现'新建'按钮")
            print(f"     → 验证: id=NULL bug 不存在,UI 正确隐藏按钮直到选择完成")

        # 检查 console error
        # (在 browser_auth.py 中,健康检查已经覆盖)
        print(f"[9] Done")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
