# -*- coding: utf-8 -*-
"""Check if forceClearChecked is available"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI()
try:
    cli.authenticated_navigate(
        '/system/archdata?productId=1&versionId=1',
        wait_for_selector='.multi-object-management',
        timeout=20000
    )

    # wait for forceClearChecked
    try:
        cli.wait_for_function(
            "() => { const t = document.querySelectorAll('.el-tree'); if (t.length < 2) return false; const c = t[1].__vueParentComponent; while (c && c.type && c.type.__name !== 'RelationScopeSection') c = c.parent; return c && typeof c.proxy.forceClearChecked === 'function'; }",
            timeout=30000
        )
        print("[Wait] forceClearChecked is available")
    except Exception as e:
        print(f"[Wait] Timeout or error: {e}")

    result = cli.evaluate(
        "() => { const t = document.querySelectorAll('.el-tree'); if (t.length < 2) return 'no trees'; const c = t[1].__vueParentComponent; while (c && c.type && c.type.__name !== 'RelationScopeSection') c = c.parent; if (!c) return 'no comp'; const exp = c.proxy; return { has: typeof exp.forceClearChecked === 'function', keys: Object.keys(exp).filter(k => typeof exp[k] === 'function') }; }"
    )
    print(f"[Check] {result}")
    cli.screenshot('check_build.png')
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()
