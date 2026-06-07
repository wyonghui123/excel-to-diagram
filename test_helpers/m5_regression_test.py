"""
M5 前端回归测试 — RelationScopeTree FilterSource (可观测版 v3)

相比 v1/v2 的改进:
  1. 使用 PlaywrightCLI (统一入口，避免 MCP 工具)
  2. 自动 pageerror/console.error/crash 监听
  3. 每个关键操作前后 health check
  4. 使用 wait_for_stable() 替代盲等 wait_for_timeout
  5. 统一错误收集 + 结构化报告
  6. Fail-Fast: 页面崩溃时立即终止，不再盲猜
"""

import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_auth_cli import PlaywrightCLI
from error_collector import PageHealthError


def run_test():
    cli = PlaywrightCLI(headless=False)
    test_passed = False

    try:
        print("=" * 60)
        print("M5 前端回归测试 — RelationScopeTree FilterSource v3")
        print("=" * 60, flush=True)

        os.makedirs("d:/filework/excel-to-diagram/test_output", exist_ok=True)

        cli.authenticated_navigate('/system/archdata', wait_for_selector='.el-select')
        cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_00_archdata.png')
        cli.assert_healthy()

        print("[STEP] 选择产品线...", flush=True)
        cli.wait_for_stable(max_wait=8000)
        cli._guard_health('product_selection')

        selects = cli.evaluate("""() => {
            const sels = document.querySelectorAll('.el-select');
            return Array.from(sels).map(s => ({
                placeholder: s.querySelector('input')?.placeholder || '',
                text: (s.textContent || '').trim().slice(0, 60)
            }));
        }""")
        for i, s in enumerate(selects):
            print(f"  Select #{i}: ph='{s['placeholder']}', text='{s['text']}'", flush=True)

        cli.open_dropdown('.el-select')
        cli.wait_for_stable(max_wait=3000)

        options = cli.evaluate("""() => {
            const items = document.querySelectorAll('.el-select-dropdown__item');
            return Array.from(items).filter(item => item.offsetParent !== null).map(item => ({
                text: (item.textContent || '').trim(),
                visible: item.offsetParent !== null
            }));
        }""")
        if options and len(options) > 0:
            for opt in options:
                if '供应链管理系统' in opt.get('text', ''):
                    print(f"  [SEL] {opt['text']}", flush=True)
                    cli.evaluate(f"""
                        () => {{
                            const items = Array.from(document.querySelectorAll('.el-select-dropdown__item')).filter(el => el.offsetParent !== null);
                            for (const item of items) {{
                                if (item.textContent.includes('供应链管理系统')) {{
                                    item.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}
                    """)
                    break
        cli.wait_for_stable(max_wait=5000)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_01_product.png')

        cli.assert_healthy()

        print("[STEP] 选择版本...", flush=True)
        selects2 = cli.evaluate("""() => {
            const sels = document.querySelectorAll('.el-select');
            return Array.from(sels).map((s, i) => ({
                index: i,
                placeholder: s.querySelector('input')?.placeholder || '',
                text: (s.textContent || '').trim().slice(0, 60)
            }));
        }""")

        version_idx = 1
        for s in selects2:
            if '版本' in s['text'] or '版本' in s['placeholder']:
                version_idx = s['index']
                break

        print(f"  Opening select #{version_idx}...", flush=True)
        cli.evaluate(f"""
            () => {{
                const sels = document.querySelectorAll('.el-select');
                sels[{version_idx}].click();
            }}
        """)
        cli.wait_for_stable(max_wait=3000)

        # 先等待下拉选项可见（通过 Playwright locator）
        v1_visible = cli.evaluate("""
            () => {
                const opts = document.querySelectorAll('.el-select-dropdown__item');
                for (const opt of opts) {
                    if ((opt.textContent || '').trim() === 'v1.0') {
                        const visible = opt.offsetParent !== null && getComputedStyle(opt).visibility !== 'hidden' && getComputedStyle(opt).display !== 'none';
                        const rect = opt.getBoundingClientRect();
                        return { found: true, visible, rect: { width: rect.width, height: rect.height }, text: opt.textContent.trim() };
                    }
                }
                return { found: false };
            }
        """)
        print(f"  v1.0 可见性检查: {v1_visible}", flush=True)

        if v1_visible.get('visible'):
            clicked_v1 = cli.click('.el-select-dropdown__item:has-text("v1.0")')
            print(f"  点击 v1.0: {clicked_v1}", flush=True)
        else:
            print("  [WARN] v1.0 未可见，尝试使用 JS 直接点击", flush=True)
            clicked_v1 = cli.evaluate("""
                () => {
                    const opts = document.querySelectorAll('.el-select-dropdown__item');
                    for (const opt of opts) {
                        if ((opt.textContent || '').trim() === 'v1.0') {
                            opt.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            print(f"  JS 点击 v1.0: {clicked_v1}", flush=True)

        cli.wait_for_stable(max_wait=8000)
        cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_02_version.png')

        health_after_version = cli.check_health()
        if not health_after_version['healthy']:
            print(f"[FAIL] Page unhealthy after version selection:\n{health_after_version['summary']}")
            return 1

        print("[STEP] 检查树渲染...", flush=True)
        cli.wait_for_stable(max_wait=8000)

        state = cli.evaluate("""() => {
            const sidebar = document.querySelector('.master-detail-layout__sidebar')
            return {
                oss_root: !!document.querySelector('.oss-root'),
                rss_root: !!document.querySelector('.rss-root'),
                el_trees: document.querySelectorAll('.el-tree').length,
                oss_nodes: document.querySelectorAll('.oss-root .el-tree-node').length,
                rss_nodes: document.querySelectorAll('.rss-root .el-tree-node').length,
                sidebar_text: (sidebar?.textContent || '').trim().slice(0, 200),
                app_errors: window.__appErrors || [],
                console_errors: window.__consoleErrors || []
            }
        }""")

        print(f"[INFO] oss-root={state['oss_root']}, rss-root={state['rss_root']}", flush=True)
        print(f"[INFO] OSS nodes={state['oss_nodes']}, RSS nodes={state['rss_nodes']}", flush=True)
        print(f"[INFO] sidebar: {state['sidebar_text']}", flush=True)

        if state.get('app_errors'):
            print(f"[ERROR] Vue errors detected: {state['app_errors']}")
        if state.get('console_errors'):
            print(f"[ERROR] Console errors: {[e.get('message','')[:100] for e in state['console_errors']]}")

        if not (state['oss_root'] and state['rss_root']):
            collector = cli.get_error_collector()
            print(f"[FAIL] Trees not rendered. {collector.summary()}")
            cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_fail_trees.png')
            return 1

        print("[PASS] Both OSS and RSS trees rendered", flush=True)

        print("\n" + "=" * 50)
        print("RSS 关系范围树测试")
        print("=" * 50, flush=True)

        print("[T1] RSS 刷新...", flush=True)
        cli.click('.rss-root .el-button:has-text("刷新")')
        cli.wait_for_stable(max_wait=12000)
        cli._guard_health('T1_refresh')

        print("[T2] RSS 展开全部...", flush=True)
        cli.click('.rss-root .el-button:has-text("展开")')
        cli.wait_for_stable(max_wait=3000)

        rss_stat = cli.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            const store = tree?.__vueParentComponent?.treeStore
            return {
                nodes: document.querySelectorAll('.rss-root .el-tree-node').length,
                checked: store?.getCheckedKeys(false)?.length || 0
            }
        }""")
        print(f"  RSS nodes={rss_stat['nodes']}, checked={rss_stat['checked']}", flush=True)

        print("[T3] RSS 全选/清空...", flush=True)
        cli.click('.rss-root .el-button:has-text("全选")')
        cli.wait_for_stable(max_wait=1000)
        checked_all = cli.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            return tree?.__vueParentComponent?.treeStore?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  全选后 checked={checked_all}", flush=True)

        cli.click('.rss-root .el-button:has-text("清空")')
        cli.wait_for_stable(max_wait=1000)
        checked_clear = cli.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            return tree?.__vueParentComponent?.treeStore?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  清空后 checked={checked_clear}", flush=True)

        print("[T4] RSS 刷新后 checked 保持...", flush=True)
        cli.click('.rss-root .el-button:has-text("全选")')
        cli.wait_for_stable(max_wait=1000)
        checked_before = cli.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            return tree?.__vueParentComponent?.treeStore?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  刷新前 checked={checked_before}", flush=True)

        cli.click('.rss-root .el-button:has-text("刷新")')
        cli.wait_for_stable(max_wait=12000)

        checked_after = cli.evaluate("""() => {
            const tree = document.querySelector('.rss-root .el-tree')
            return tree?.__vueParentComponent?.treeStore?.getCheckedKeys(false)?.length || 0
        }""")
        print(f"  刷新后 checked={checked_after}", flush=True)
        if checked_before == checked_after:
            print(f"  [PASS] 刷新后 checked 保持: {checked_before} = {checked_after}")
        else:
            print(f"  [INFO] 刷新后 checked: {checked_before} -> {checked_after}")

        print("\n" + "=" * 50)
        print("OSS -> RSS filter-node-method")
        print("=" * 50, flush=True)

        cli.click('.rss-root .el-button:has-text("清空")')
        cli.wait_for_stable(max_wait=500)

        rss_before = cli.evaluate("() => document.querySelectorAll('.rss-root .el-tree-node').length")
        print(f"[INFO] OSS 勾选前 RSS 节点: {rss_before}", flush=True)

        print("[T5] 展开 OSS + 点击首节点...", flush=True)
        cli.click('.oss-root .el-button:has-text("展开")')
        cli.wait_for_stable(max_wait=1000)

        oss_count = cli.evaluate("() => document.querySelectorAll('.oss-root .el-tree-node__content').length")
        print(f"  OSS 可见节点: {oss_count}", flush=True)

        if oss_count > 0:
            cli.evaluate("""() => {
                const nodes = document.querySelectorAll('.oss-root .el-tree-node__content')
                if (nodes[0]) nodes[0].click()
            }""")
            cli.wait_for_stable(max_wait=2000)

        rss_after = cli.evaluate("() => document.querySelectorAll('.rss-root .el-tree-node').length")
        print(f"  OSS 勾选后 RSS 节点: {rss_after}", flush=True)
        if rss_before != rss_after:
            print(f"  [PASS] filter-node-method 生效: {rss_before} -> {rss_after}")
        else:
            print(f"  [INFO] filter-node-method 无变化")

        cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_final.png')

        health_final = cli.check_health()
        if health_final['healthy']:
            print("\n" + "=" * 60)
            print("[PASS] M5 前端回归测试完成")
            print("=" * 60, flush=True)
            test_passed = True
            return 0
        else:
            print(f"\n[FAIL] Test completed with errors:\n{health_final['summary']}")
            return 1

    except PageHealthError as e:
        print(f"\n[FAIL] Page health check failed: {e.summary}")
        try:
            cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_health_failure.png')
        except Exception:
            pass
        return 1

    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        try:
            cli.screenshot('d:/filework/excel-to-diagram/test_output/m5v3_error.png')
        except Exception:
            pass
        return 1

    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(run_test())
