# -*- coding: utf-8 -*-
"""E2E 验证脚本：点击 OSS 树 checkbox 后，RSS 树应显示可见子节点"""
import sys, time, json, urllib.request, urllib.error
sys.path.insert(0, 'd:/filework/excel-to-diagram')
sys.path.insert(0, 'd:/filework/excel-to-diagram/tests/e2e')

def dev_login(username="admin"):
    """通过 urllib.request 设置认证 cookie"""
    try:
        req = urllib.request.Request(
            f"http://localhost:3010/api/v1/auth/dev-login?username={username}",
            method="GET"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

def main():
    from test_helpers.browser_auth_cli import PlaywrightCLI
    cli = PlaywrightCLI(headless=False)
    results = []
    try:
        # Step 1: 通过 urllib 设置后端认证
        print("Authenticating via dev-login...")
        login_result = dev_login("admin")
        if "error" in login_result:
            print(f"[FAIL] dev-login failed: {login_result['error']}")
            cli.close()
            sys.exit(1)
        print(f"[OK] dev-login: {login_result}")

        # Step 2: 使用 browser context 访问 dev-login（设置浏览器 cookie）
        print("Setting browser cookie...")
        page = cli._ensure_browser()
        try:
            page.goto(
                "http://localhost:3010/api/v1/auth/dev-login?username=admin",
                wait_until="domcontentloaded",
                timeout=10000
            )
            time.sleep(1)
        except Exception as e:
            print(f"[WARN] Browser dev-login: {e}")

        # Step 3: 加载前端 archdata 页面
        print("Loading frontend archdata page...")
        page.goto(
            "http://localhost:3004/system/archdata?productId=1&versionId=1",
            wait_until="domcontentloaded",
            timeout=20000
        )
        print("[OK] Page loaded")

        # Step 4: 等待登录遮罩消失
        for i in range(30):
            visible = cli.evaluate(
                "(function(){var o=document.querySelector('.login-overlay');"
                "return o?getComputedStyle(o).display!=='none':false})()")
            if not visible:
                print("[OK] Login done at " + str(i) + "s")
                break
            time.sleep(1)
        else:
            print("[WARN] Login overlay still visible")

        time.sleep(2)

        # Step 5: 等待两个树渲染
        for i in range(60):
            n = cli.evaluate(
                "(function(){return document.querySelectorAll('.el-tree').length})()")
            if n >= 2:
                print("[OK] Trees rendered at " + str(i) + "s: " + str(n))
                break
            time.sleep(1)
        else:
            print("[FAIL] Trees not rendered")
            cli.close()
            sys.exit(1)

        time.sleep(1)

        # ---- 展开 RSS 关系范围面板（默认是折叠状态）----
        print("Expanding RSS relation-scope panel...")
        expand_result = cli.evaluate(
            "(function(){"
            "var panel=document.querySelector('.rst-panel-relation');"
            "if(!panel)return 'RSS panel not found';"
            "var header=panel.querySelector('.collapsible-panel__header');"
            "if(header){header.click();return 'panel expanded';}"
            "return 'no header found'})()")
        print(f"[OK] {expand_result}")

        time.sleep(1)

        # ---- TEST: 点击 OSS 树 checkbox 选择服务模块 ----
        print("\n--- Clicking OSS tree checkbox ---")

        click_result = cli.evaluate(
            "(function(){var t=document.querySelectorAll('.el-tree');"
            "var oss=t[0];if(!oss)return 'no OSS tree';"
            "var nodes=oss.querySelectorAll('.el-tree-node');"
            "for(var i=0;i<nodes.length;i++){"
            "var cb=nodes[i].querySelector('.el-checkbox');"
            "if(cb){"
            "var label=nodes[i].querySelector('.el-tree-node__label');"
            "var labelText=label?label.textContent.trim():'unknown';"
            "cb.click();"
            "return 'clicked node '+i+': '+labelText;"
            "}"
            "}"
            "return 'no clickable OSS checkbox found'})()")
        print(f"OSS click: {click_result}")

        # Step 6: 等待 2 秒让 RSS 树重新渲染
        print("Waiting 2s for RSS tree re-render...")
        time.sleep(2)

        # Step 7: 检查 RSS 树有可见子节点（使用 offsetWidth/Height）
        print("Checking RSS tree visible nodes...")
        rss_info = cli.evaluate(
            "(function(){"
            "var t=document.querySelectorAll('.el-tree');"
            "var rss=t[1];if(!rss)return JSON.stringify({error:'no RSS tree'});"
            "var nodes=rss.querySelectorAll('.el-tree-node');"
            "var visibleNodes=[];var totalVisible=0;"
            "for(var i=0;i<nodes.length;i++){"
            "var n=nodes[i];"
            "var ow=n.offsetWidth,oh=n.offsetHeight;"
            "var style=getComputedStyle(n);"
            "var hasSize=(ow>0&&oh>0);"
            "var notHidden=(style.display!=='none'&&style.visibility!=='hidden');"
            "var isVis=hasSize&&notHidden;"
            "if(isVis){"
            "totalVisible++;"
            "var text=n.textContent.trim().substring(0,80);"
            "var hasCheckbox=!!n.querySelector('.el-checkbox');"
            "visibleNodes.push({idx:i,text:text,hasCheckbox:hasCheckbox,"
            "  offset:{w:ow,h:oh}});"
            "}"
            "}"
            "return JSON.stringify({"
            "  total:nodes.length,"
            "  visible:totalVisible,"
            "  visibleNodes:visibleNodes"
            "})})()")

        rss_data = json.loads(rss_info)
        rss_total = rss_data.get('total', 0)
        rss_visible_count = rss_data.get('visible', 0)
        visible_nodes = rss_data.get('visibleNodes', [])

        print(f"RSS tree: {rss_total} total nodes, {rss_visible_count} visible nodes")

        # 显示可见节点信息
        has_checkbox_nodes = [n for n in visible_nodes if n.get('hasCheckbox')]
        same_service_nodes = [n for n in visible_nodes if '同服务模块' in (n.get('text', '') or '')]

        print(f"RSS visible checkbox nodes: {len(has_checkbox_nodes)}")
        print(f"RSS visible '同服务模块' nodes: {len(same_service_nodes)}")

        for node in visible_nodes[:8]:
            print(f"  [{node['idx']}] {node['text'][:60]} (hasCheckbox={node['hasCheckbox']})")

        # 验证 OSS 树有选中
        oss_checked = cli.evaluate(
            "(function(){var t=document.querySelectorAll('.el-tree');"
            "return t[0]?t[0].querySelectorAll('.el-checkbox__input.is-checked').length:-1})()")
        print(f"OSS checked checkboxes: {oss_checked}")

        # ---- 判定 ----
        # 条件1: RSS 树有可见节点（数量 > 0）
        # 条件2: 存在带 checkbox 的可见节点
        t1 = (rss_visible_count > 0) and (len(has_checkbox_nodes) > 0)
        results.append(t1)

        print(f"\n{'PASS' if t1 else 'FAIL'}: "
              f"RSS visible_nodes={rss_visible_count}, "
              f"visible_with_checkbox={len(has_checkbox_nodes)}, "
              f"same_service_nodes={len(same_service_nodes)}")

        print("\n=== Summary ===")
        passed = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False)
        skipped = sum(1 for r in results if r is None)
        print(f"Passed: {passed}  Failed: {failed}  Skipped: {skipped}")
        if failed > 0:
            sys.exit(1)
    finally:
        cli.close()

if __name__ == "__main__":
    main()
