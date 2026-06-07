# -*- coding: utf-8 -*-
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
            # 可能已经重定向，尝试加载首页

        # Step 3: 加载前端页面
        print("Loading frontend...")
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

        # Step 5: 等待树渲染
        for i in range(60):
            n = cli.evaluate(
                "(function(){return document.querySelectorAll('.el-tree').length})()")
            if n >= 2:
                print("[OK] Trees at " + str(i) + "s: " + str(n))
                break
            time.sleep(1)
        else:
            print("[FAIL] Trees not rendered")
            cli.close()
            sys.exit(1)

        # Step 6: 等待 forceClearChecked
        for i in range(120):
            ok = cli.evaluate(
                "(function(){var t=document.querySelectorAll('.el-tree');if(t.length<2)return false;"
                "var c=t[1].__vueParentComponent;while(c&&c.type&&c.type.__name!=='RelationScopeSection')c=c.parent;"
                "if(!c)return false;var p=c.proxy;return p&&p.$&&p.$.exposed&&typeof p.$.exposed.forceClearChecked==='function'})()")
            if ok:
                print("[OK] forceClearChecked ready at " + str(i) + "s")
                break
            time.sleep(1)
        else:
            print("[WARN] forceClearChecked not available after 120s")

        time.sleep(1)

        # ---- TEST 1 ----
        print("\n--- Test 1: forceClearChecked ---")
        cli.evaluate(
            "(function(){var t=document.querySelectorAll('.el-tree');"
            "var r=t[1];if(!r)return;var ns=r.querySelectorAll('.el-tree-node');"
            "if(ns.length>0){var c=ns[0].querySelector('.el-checkbox');if(c)c.click()}})()")
        time.sleep(1)
        c1 = cli.evaluate(
            "(function(){var t=document.querySelectorAll('.el-tree');"
            "return t[1]?t[1].querySelectorAll('.el-checkbox__input.is-checked').length:-1})()")
        print("RSS after add: " + str(c1))
        if c1 > 0:
            ok2 = cli.evaluate(
                "(function(){var t=document.querySelectorAll('.el-tree');if(t.length<2)return false;"
                "var c=t[1].__vueParentComponent;while(c&&c.type&&c.type.__name!=='RelationScopeSection')c=c.parent;"
                "if(!c)return false;var p=c.proxy;if(p&&p.$&&p.$.exposed&&typeof p.$.exposed.forceClearChecked==='function'){"
                "p.$.exposed.forceClearChecked();return true}return false})()")
            print("forceClearChecked: " + str(ok2))
            time.sleep(1)
            c2 = cli.evaluate(
                "(function(){var t=document.querySelectorAll('.el-tree');"
                "return t[1]?t[1].querySelectorAll('.el-checkbox__input.is-checked').length:-1})()")
            print("RSS after clear: " + str(c2))
            t1 = (c2 == 0)
            results.append(t1)
            print(("PASS" if t1 else "FAIL") + " Test 1 c1=" + str(c1) + "->c2=" + str(c2))
        else:
            print("SKIP Test 1: no RSS selection")
            results.append(None)

        # ---- TEST 2 ----
        print("\n--- Test 2: OSS click clears RSS ---")
        cli.evaluate(
            "(function(){var t=document.querySelectorAll('.el-tree');"
            "var r=t[1];if(!r)return;var ns=r.querySelectorAll('.el-tree-node');"
            "if(ns.length>0){var c=ns[0].querySelector('.el-checkbox');if(c)c.click()}})()")
        time.sleep(1)
        c_before = cli.evaluate(
            "(function(){var t=document.querySelectorAll('.el-tree');"
            "return t[1]?t[1].querySelectorAll('.el-checkbox__input.is-checked').length:-1})()")
        print("RSS before OSS: " + str(c_before))
        if c_before > 0:
            cli.evaluate(
                "(function(){var t=document.querySelectorAll('.el-tree');"
                "var o=t[0];if(!o)return;var ns=o.querySelectorAll('.el-tree-node');"
                "for(var i=0;i<ns.length;i++){var c=ns[i].querySelector('.el-checkbox');if(c){c.click();break}}})()")
            time.sleep(2)
            c_after = cli.evaluate(
                "(function(){var t=document.querySelectorAll('.el-tree');"
                "return t[1]?t[1].querySelectorAll('.el-checkbox__input.is-checked').length:-1})()")
            print("RSS after OSS: " + str(c_after))
            t2 = (c_after == 0)
            results.append(t2)
            print(("PASS" if t2 else "FAIL") + " Test 2")
        else:
            print("SKIP Test 2: no RSS selection")
            results.append(None)

        print("\n=== Summary ===")
        passed = sum(1 for r in results if r is True)
        failed = sum(1 for r in results if r is False)
        skipped = sum(1 for r in results if r is None)
        print("Passed: " + str(passed) + " Failed: " + str(failed) + " Skipped: " + str(skipped))
        if failed > 0:
            sys.exit(1)
    finally:
        cli.close()

if __name__ == "__main__":
    main()
