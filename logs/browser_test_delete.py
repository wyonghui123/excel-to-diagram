# -*- coding: utf-8 -*-
"""
[FIX 2026-06-12] 真实浏览器 UI 测试：用户组/产品删除限制是否在 UI 生效
"""
import asyncio
import json
import sys
import urllib.request

from playwright.async_api import async_playwright


def http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    if data is not None:
        req.data = data
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


async def login_via_api():
    body = json.dumps({"username": "admin", "password": "admin123"}).encode()
    status, data = http("POST", "http://localhost:3010/api/v2/action/user.authenticate",
                        headers={"Content-Type": "application/json"}, data=body)
    j = json.loads(data)
    return j["data"]["token"]


def find_ug_with_member(token):
    """找一个有成员的用户组"""
    status, data = http("GET", "http://localhost:3010/api/v2/bo/user_group_member?page=1&page_size=5",
                        headers={"Cookie": f"auth_token={token}"})
    items = json.loads(data)["data"]["items"]
    if not items:
        return None, None
    group_id = items[0]["group_id"]
    status, data = http("GET", f"http://localhost:3010/api/v2/bo/user_group/{group_id}",
                        headers={"Cookie": f"auth_token={token}"})
    group = json.loads(data)["data"]
    return group, items[0]


def find_product_with_version(token):
    """找一个有版本的产品"""
    status, data = http("GET", "http://localhost:3010/api/v2/bo/version?page=1&page_size=1",
                        headers={"Cookie": f"auth_token={token}"})
    versions = json.loads(data)["data"]["items"]
    if not versions:
        return None, None
    product_id = versions[0]["product_id"]
    status, data = http("GET", f"http://localhost:3010/api/v2/bo/product/{product_id}",
                        headers={"Cookie": f"auth_token={token}"})
    product = json.loads(data)["data"]
    return product, versions[0]


async def main():
    base_url = "http://localhost:3004"  # Vite 前端
    results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        failed_requests = []
        page.on("response", lambda r: failed_requests.append((r.status, r.url)) if r.status >= 400 else None)

        # 注入 Notification 监听 (Element Plus 弹窗)
        await page.add_init_script("""
          window.__notifs = [];
          const obs = new MutationObserver((mutations) => {
            for (const m of mutations) {
              for (const n of m.addedNodes) {
                if (n.nodeType !== 1) continue;
                const cls = (n.className && n.className.toString) ? n.className.toString() : '';
                if (cls.includes('el-notification') || cls.includes('el-message') || cls.includes('el-message-box')) {
                  setTimeout(() => {
                    const txt = (n.textContent || '').trim().slice(0, 200);
                    if (txt) {
                      window.__notifs.push(txt);
                      console.log('[NOTIF]', txt);
                    }
                  }, 50);
                }
              }
            }
          });
          if (document.body) obs.observe(document.body, { childList: true, subtree: true });
          else document.addEventListener('DOMContentLoaded', () => obs.observe(document.body, { childList: true, subtree: true }));
        """)

        # 1) 登录拿 token
        print("=" * 70)
        print("STEP 1: Login (API)")
        print("=" * 70)
        token = await login_via_api()
        await context.add_cookies([{
            "name": "auth_token", "value": token, "domain": "localhost", "path": "/"
        }])
        print(f"  token len = {len(token)}")

        # 2) 找 user_group + member
        print()
        print("=" * 70)
        print("STEP 2: find user_group with member")
        print("=" * 70)
        ug, member = find_ug_with_member(token)
        if not ug:
            print("  [SKIP] no user_group with member")
        else:
            print(f"  group: id={ug['id']} name={ug.get('name', '')}")
            print(f"  member: group_id={member['group_id']} user_id={member['user_id']}")

            # 3) 访问 /user-permission?tab=user-groups
            print()
            print("=" * 70)
            print("STEP 3: navigate to user-groups page")
            print("=" * 70)
            # 先清空一下 notifications (reset listener)
            await page.goto("about:blank")
            await page.add_init_script("window.__notifs = [];")
            await page.goto(f"{base_url}/user-permission?tab=user-groups")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            print(f"  URL: {page.url}")
            print(f"  TITLE: {await page.title()}")
            await page.screenshot(path="d:/filework/excel-to-diagram/_test_ug_page.png", full_page=True)

            # 检查是否有表格
            html = await page.content()
            has_table = 'el-table' in html or '<table' in html
            print(f"  has table: {has_table}")
            print(f"  has group name in page: {ug.get('name', '') in html}")
            # 找包含 group name 或 code 的元素
            cell_count = await page.locator(f"text={ug.get('name', '')}").count()
            code_count = await page.locator(f"text={ug.get('code', '')}").count()
            print(f"  cell count for name='{ug.get('name', '')}': {cell_count}, code='{ug.get('code', '')}': {code_count}")

            # 尝试批量删除流程
            print()
            print("  Attempting batch-delete flow: select row + click batch delete...")
            try:
                # 1) 勾选该行
                row = page.locator(f"tr:has-text(\"{ug.get('name', '')}\"), tr:has-text(\"{ug.get('code', '')}\")").first
                if await row.count() == 0:
                    print("  [WARN] row not found")
                else:
                    # 该行第一列是 checkbox label
                    chk_label = row.locator(".el-checkbox").first
                    if await chk_label.count() > 0:
                        # el-checkbox 的 input 是 hidden, 需要点 label/span
                        await chk_label.click(force=True)
                        await page.wait_for_timeout(500)
                        print("  selected row")
                    else:
                        print(f"  [WARN] no checkbox in row")

                    await page.screenshot(path="d:/filework/excel-to-diagram/_test_ug_selected.png", full_page=True)

                    # 2) 找批量删除按钮 (选中后才会出现)
                    # 看看 toolbar 上有什么新按钮
                    toolbar_buttons = await page.locator(".toolbar button, .list-toolbar button, .el-button").all()
                    print(f"  toolbar buttons: {len(toolbar_buttons)}")
                    for b in toolbar_buttons[:10]:
                        text = (await b.text_content() or "").strip()
                        cls = await b.get_attribute("class")
                        print(f"    btn: text={text!r}, class={(cls or '')[:80]}")

                    batch_del = page.locator("button:has-text('批量删除'), button:has-text('删除'), .batch-delete-btn").last
                    print(f"  batch delete btn found: {await batch_del.count() > 0}")
                    if await batch_del.count() > 0:
                        await batch_del.click()
                        await page.wait_for_timeout(800)
                        await page.screenshot(path="d:/filework/excel-to-diagram/_test_ug_batch.png", full_page=True)
                        # 确认弹窗
                        confirm = page.locator(".el-message-box .el-button--primary, .el-message-box button:has-text('确定'), .el-message-box button:has-text('是'), .el-message-box button:has-text('确认')").last
                        if await confirm.count() > 0:
                            await confirm.click()
                            await page.wait_for_timeout(3000)
                            notifs = await page.evaluate("window.__notifs || []")
                            body_text = await page.text_content("body")
                            has_member = any('成员' in n for n in notifs) or '成员' in (body_text or '')
                            has_success = any('删除成功' in n for n in notifs) or '删除成功' in (body_text or '')
                            await page.screenshot(path="d:/filework/excel-to-diagram/_test_ug_batch_done.png", full_page=True)
                            print(f"  notifications: {notifs}")
                            if has_member and not has_success:
                                print("  ✅ TEST PASSED: 批量删除含成员组时弹'成员'错误")
                                results.append(("UG batch delete blocked (UI)", True, str(notifs)))
                            elif has_success:
                                print("  ❌ TEST FAILED: 弹了 '删除成功'")
                                results.append(("UG batch delete blocked (UI)", False, str(notifs)))
                            else:
                                print(f"  [WARN] no member/success, body has 成员: {'成员' in (body_text or '')}")
                                results.append(("UG batch delete blocked (UI)", False, "no notif"))
                        else:
                            print("  [WARN] no confirm button")
                            results.append(("UG batch delete blocked (UI)", False, "no confirm"))
                    else:
                        # 兜底：点组名进详情页
                        print("  no batch delete in toolbar, try detail page...")
                        code_link = row.locator(".bk-link").first
                        if await code_link.count() > 0:
                            await code_link.click()
                            await page.wait_for_timeout(3000)
                            await page.screenshot(path="d:/filework/excel-to-diagram/_test_ug_detail.png", full_page=True)
                            # 找详情页删除按钮
                            detail_del = page.locator("button:has-text('删除'), .detail-delete-btn, [class*='delete'] button").first
                            if await detail_del.count() > 0:
                                await detail_del.click()
                                await page.wait_for_timeout(800)
                                confirm = page.locator(".el-message-box .el-button--primary, .el-message-box button:has-text('确定')").last
                                if await confirm.count() > 0:
                                    await confirm.click()
                                    await page.wait_for_timeout(3000)
                                    notifs = await page.evaluate("window.__notifs || []")
                                    body_text = await page.text_content("body")
                                    has_member = any('成员' in n for n in notifs) or '成员' in (body_text or '')
                                    has_success = any('删除成功' in n for n in notifs) or '删除成功' in (body_text or '')
                                    if has_member and not has_success:
                                        print("  ✅ TEST PASSED: 详情页删除含成员组时弹'成员'错误")
                                        results.append(("UG detail delete blocked (UI)", True, str(notifs)))
                                    else:
                                        print(f"  ❌ TEST FAILED: notifs={notifs}, has_success={has_success}")
                                        results.append(("UG detail delete blocked (UI)", False, str(notifs)))
                            else:
                                print("  [WARN] no detail delete btn")
                                results.append(("UG delete blocked (UI)", False, "no detail del"))
                        else:
                            results.append(("UG delete blocked (UI)", False, "no batch+no link"))
            except Exception as e:
                import traceback
                traceback.print_exc()
                results.append(("UG delete blocked (UI)", False, str(e)))

            # 4) 用前端 fetch 模拟完整流程, 走 httpClient 包装
            print()
            print("=" * 70)
            print("STEP 4: simulate front-end fetch DELETE (with httpClient path)")
            print("=" * 70)
            result = await page.evaluate(f"""
              async () => {{
                const r = await fetch('/api/v2/bo/user_group/{ug['id']}', {{
                  method: 'DELETE',
                  credentials: 'include'
                }});
                return {{ status: r.status, body: await r.text() }};
              }}
            """)
            print(f"  status: {result['status']}")
            print(f"  body: {result['body'][:400]}")
            decoded = result["body"].encode().decode("unicode_escape")
            print(f"  decoded: {decoded[:400]}")
            success_in_body = '"success":true' in result["body"]
            contains_member = "成员" in decoded
            if not success_in_body and contains_member:
                print("  ✅ TEST PASSED (fetch): 400 + '用户组下还有成员'")
                results.append(("UG delete blocked (fetch)", True, decoded[:200]))
            else:
                print("  ❌ TEST FAILED (fetch)")
                results.append(("UG delete blocked (fetch)", False, decoded[:200]))

        # 5) 产品 + 版本
        print()
        print("=" * 70)
        print("STEP 5: product with version (fetch)")
        print("=" * 70)
        product, version = find_product_with_version(token)
        if not product:
            print("  [SKIP] no product with version")
        else:
            print(f"  product: id={product['id']} name={product.get('name', '')}")
            result = await page.evaluate(f"""
              async () => {{
                const r = await fetch('/api/v2/bo/product/{product['id']}', {{
                  method: 'DELETE',
                  credentials: 'include'
                }});
                return {{ status: r.status, body: await r.text() }};
              }}
            """)
            print(f"  status: {result['status']}")
            print(f"  body: {result['body'][:400]}")
            decoded = result["body"].encode().decode("unicode_escape")
            print(f"  decoded: {decoded[:400]}")
            success_in_body = '"success":true' in result["body"]
            contains_child = "子元素" in decoded or "版本" in decoded
            if not success_in_body and contains_child:
                print("  ✅ TEST PASSED: 400 + '子元素/版本'")
                results.append(("Product delete blocked", True, decoded[:200]))
            else:
                print("  ❌ TEST FAILED")
                results.append(("Product delete blocked", False, decoded[:200]))

        # 6) 验证 DB 中数据未被删除 (最关键)
        print()
        print("=" * 70)
        print("STEP 6: verify data still in DB (CRITICAL)")
        print("=" * 70)
        if ug:
            status, data = http("GET", f"http://localhost:3010/api/v2/bo/user_group/{ug['id']}",
                                headers={"Cookie": f"auth_token={token}"})
            ug_still = status == 200
            print(f"  user_group {ug['id']} still exists: {ug_still}")
            if not ug_still:
                print("  ❌❌❌ CRITICAL: user_group was deleted despite RESTRICT!")
                results.append(("DB integrity UG", False, "deleted"))
            else:
                print(f"  ✅ user_group {ug['id']} preserved")
                results.append(("DB integrity UG", True, "preserved"))
        if product:
            status, data = http("GET", f"http://localhost:3010/api/v2/bo/product/{product['id']}",
                                headers={"Cookie": f"auth_token={token}"})
            prod_still = status == 200
            print(f"  product {product['id']} still exists: {prod_still}")
            if not prod_still:
                print("  ❌❌❌ CRITICAL: product was deleted despite RESTRICT!")
                results.append(("DB integrity Product", False, "deleted"))
            else:
                print(f"  ✅ product {product['id']} preserved")
                results.append(("DB integrity Product", True, "preserved"))

        await browser.close()

    # FAILED REQUESTS
    print()
    print("=" * 70)
    print("FAILED REQUESTS (status >= 400)")
    print("=" * 70)
    for status, url in failed_requests:
        if "authenticate" in url or "dev-login" in url:
            continue
        print(f"  [{status}] {url[:200]}")

    # SUMMARY
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    passed = sum(1 for _, p, _ in results if p)
    for name, p, msg in results:
        mark = "✅" if p else "❌"
        print(f"  {mark} {name}: {msg[:200]}")
    print()
    print(f"  {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
