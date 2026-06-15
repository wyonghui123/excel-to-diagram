"""
真实浏览器 e2e 验证 — 闭环测试 (v3)
所有输出写文件，避免 buffer 问题
"""
import asyncio
import re
import sys
import json
from playwright.async_api import async_playwright

FRONTEND_URL = "http://localhost:3004"
LOGIN_URL = f"{FRONTEND_URL}/#/login"
LOG_FILE = "d:/filework/_e2e_out.log"

API_CALLS = []


def flog(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(str(msg) + "\n")


async def main():
    # 清空 log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        async def on_request(req):
            url = req.url
            if "/api/v2/bo/relationship" in url or "/bo/relationship" in url:
                API_CALLS.append({"method": req.method, "url": url})
                flog(f"[API] {req.method} {url}")

        page.on("request", on_request)
        page.on("pageerror", lambda e: flog(f"[PAGEERROR] {e}"))

        # 1. 登录
        flog("=" * 80)
        flog("Step 1: 登录")
        flog("=" * 80)
        await page.goto(LOGIN_URL, wait_until="networkidle")
        await page.wait_for_timeout(2000)
        inputs = await page.locator("input").all()
        await inputs[0].fill("admin")
        await inputs[1].fill("admin123")
        await page.locator("button.login-btn").first.click()
        await page.wait_for_timeout(3000)
        flog(f"After login URL: {page.url}")

        # 2. 进数据管理页
        flog("=" * 80)
        flog("Step 2: 进架构数据管理")
        flog("=" * 80)
        await page.goto(f"{FRONTEND_URL}/#/data-manager?menu=architecture&_t=1", wait_until="networkidle")
        await page.wait_for_timeout(3000)

        all_cards = await page.locator("text=架构数据管理").all()
        clicked = False
        for el in all_cards:
            if await el.is_visible():
                await el.click(force=True)
                clicked = True
                break
        flog(f"Card clicked: {clicked}")
        await page.wait_for_timeout(5000)
        flog(f"URL: {page.url}")

        # 3. 选产品 + 版本
        flog("=" * 80)
        flog("Step 3: 选产品 + 版本")
        flog("=" * 80)

        async def pick_option_by_text(idx, label, text_match):
            """Select option with text matching text_match (substring)"""
            selects = await page.locator(".el-select").all()
            flog(f"[{label}] {len(selects)} selects, using {idx}, looking for: {text_match!r}")
            if idx >= len(selects):
                return False
            await selects[idx].click(force=True)
            await page.wait_for_timeout(2000)
            for attempt in range(8):
                options = await page.locator(".el-select-dropdown__item:visible").all()
                flog(f"[{label}] attempt {attempt}: visible options = {len(options)}")
                if options:
                    found = None
                    for i, o in enumerate(options):
                        t = (await o.text_content() or "").strip()
                        flog(f"  [{i}] {t!r}")
                        if text_match in t:
                            found = o
                            flog(f"  MATCH! [{i}] {t!r}")
                            break
                    if found:
                        await found.click(force=True)
                        await page.wait_for_timeout(3000)
                        return True
                    # 没找到匹配项, 用第一个
                    await options[0].click(force=True)
                    await page.wait_for_timeout(3000)
                    return True
                await page.wait_for_timeout(1000)
            return False

        # 选 供应链管理系统 产品
        await pick_option_by_text(0, "Product", "供应链")
        # 选 新测试2 版本
        await pick_option_by_text(1, "Version", "新测试")

        # 等待数据加载
        await page.wait_for_timeout(5000)
        await page.screenshot(path="d:/filework/_e2e_after_pv.png", full_page=True)
        flog("Screenshot: _e2e_after_pv.png")

        # 4. 找 采购管理领域
        flog("=" * 80)
        flog("Step 4: 找 采购管理领域")
        flog("=" * 80)
        # 滚动左侧 tree 到顶
        try:
            tree_container = page.locator(".el-tree").first
            await tree_container.evaluate("el => el.scrollTop = 0")
            flog("Scrolled tree to top")
        except Exception as e:
            flog(f"Scroll error: {e}")

        # 用 text= 找 采购管理 (即使不可见也在 DOM 中)
        target_text = page.locator("text=采购管理").first
        if await target_text.count() > 0:
            flog("Found 采购管理 text element")
            await target_text.scroll_into_view_if_needed()
            await page.wait_for_timeout(500)
            # 找最近的 tree-node 容器
            try:
                # Element Plus tree node 包含 label + checkbox
                # 用 closest 找 .el-tree-node 祖先
                node_handle = await target_text.evaluate_handle("el => el.closest('.el-tree-node')")
                if node_handle:
                    cb = page.locator(".el-checkbox").first  # 第一个 checkbox in the node
                    # 用 evaluate 直接点 checkbox
                    clicked = await node_handle.evaluate("""node => {
                        const cb = node.querySelector('.el-checkbox');
                        if (cb) {
                            const inner = cb.querySelector('.el-checkbox__input') || cb.querySelector('.el-checkbox__inner') || cb;
                            inner.click();
                            return true;
                        }
                        return false;
                    }""")
                    flog(f"Clicked via evaluate: {clicked}")
            except Exception as e:
                flog(f"Click error: {e}")
                await target_text.click(force=True)
        else:
            flog("WARN: 没找到 采购管理 text")
        await page.wait_for_timeout(3000)
        await page.screenshot(path="d:/filework/_e2e_after_procurement.png", full_page=True)

        # 5. 勾选 范围内
        flog("=" * 80)
        flog("Step 5: 展开 关系范围 + 勾选 范围内")
        flog("=" * 80)
        API_CALLS.clear()
        flog(f"API_CALLS cleared")

        # 展开 关系范围 section (在左侧 sidebar 底部)
        try:
            rs_header = page.locator("text=关系范围").first
            if await rs_header.count() > 0:
                # 找最近的 section header (不是 tree 节点里的标签)
                # 关系范围 section header 通常是 sidebar 区域
                await rs_header.scroll_into_view_if_needed()
                # 找 header 容器 - 可能是 div 包含文字
                rs_section = await rs_header.evaluate_handle("""el => {
                    // 找最近的 section header
                    let cur = el;
                    while (cur && cur.parentElement) {
                        const style = window.getComputedStyle(cur);
                        if (cur.classList && (cur.classList.contains('section-header') ||
                            cur.classList.contains('collapsible') ||
                            cur.getAttribute('role') === 'button' ||
                            cur.classList.contains('el-collapse-item__header'))) {
                            return cur;
                        }
                        cur = cur.parentElement;
                    }
                    return el.parentElement;
                }""")
                if rs_section:
                    await rs_section.as_element().click(force=True)
                    flog("Clicked 关系范围 section header")
                    await page.wait_for_timeout(2000)
        except Exception as e:
            flog(f"Expand 关系范围 error: {e}")

        await page.screenshot(path="d:/filework/_e2e_5a_expanded.png", full_page=True)

        # 找 范围内 节点 (用 text= 模糊匹配)
        within_target = page.locator("text=范围内").first
        within_count = await page.locator("text=范围内").count()
        flog(f"Found {within_count} '范围内' elements")
        if within_count > 0:
            # 用 evaluate 直接找最近的 tree-node 并点击 checkbox
            try:
                clicked = await within_target.evaluate("""el => {
                    // 找最近的 tree-node 祖先
                    let cur = el;
                    while (cur && !cur.classList?.contains('el-tree-node')) {
                        cur = cur.parentElement;
                    }
                    if (!cur) return 'no-tree-node';
                    const cb = cur.querySelector('.el-checkbox');
                    if (!cb) return 'no-checkbox';
                    const inner = cb.querySelector('.el-checkbox__inner') || cb.querySelector('.el-checkbox__input') || cb;
                    inner.click();
                    return 'clicked';
                }""")
                flog(f"Clicked 范围内 via evaluate: {clicked}")
            except Exception as e:
                flog(f"Click error: {e}")
        else:
            flog("WARN: 没找到 范围内")
        await page.wait_for_timeout(3000)
        flog(f"API calls after 范围内: {len(API_CALLS)}")
        for c in API_CALLS:
            flog(f"  {c['method']} {c['url']}")
        await page.screenshot(path="d:/filework/_e2e_after_within.png", full_page=True)

        # 6. 勾选 范围内与外部
        flog("=" * 80)
        flog("Step 6: 勾选 范围内与外部")
        flog("=" * 80)
        API_CALLS.clear()
        within_ext_target = page.locator("text=范围内与外部").first
        within_ext_count = await page.locator("text=范围内与外部").count()
        flog(f"Found {within_ext_count} '范围内与外部' elements")
        if within_ext_count > 0:
            try:
                clicked = await within_ext_target.evaluate("""el => {
                    let cur = el;
                    while (cur && !cur.classList?.contains('el-tree-node')) {
                        cur = cur.parentElement;
                    }
                    if (!cur) return 'no-tree-node';
                    const cb = cur.querySelector('.el-checkbox');
                    if (!cb) return 'no-checkbox';
                    const inner = cb.querySelector('.el-checkbox__inner') || cb.querySelector('.el-checkbox__input') || cb;
                    inner.click();
                    return 'clicked';
                }""")
                flog(f"Clicked 范围内与外部 via evaluate: {clicked}")
            except Exception as e:
                flog(f"Click error: {e}")
        else:
            flog("WARN: 没找到 范围内与外部")
        await page.wait_for_timeout(3000)
        flog(f"API calls after 范围内与外部: {len(API_CALLS)}")
        for c in API_CALLS:
            flog(f"  {c['method']} {c['url']}")
        await page.screenshot(path="d:/filework/_e2e_after_within_ext.png", full_page=True)

        # 保存
        with open("d:/filework/_e2e_final_apis.json", "w", encoding="utf-8") as f:
            json.dump(API_CALLS, f, ensure_ascii=False, indent=2)
        flog(f"Saved {len(API_CALLS)} API calls to d:/filework/_e2e_final_apis.json")

        await browser.close()
        flog("DONE")


asyncio.run(main())
