"""
v40.1 修复 E2E 验证 v3 - 浏览器内挂载测试组件
"""
import asyncio
import os
import sys
import traceback
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3004"
API_URL = "http://localhost:3010"
SCREENSHOT_DIR = "d:/filework/excel-to-diagram/test_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()

        try:
            print("=" * 70)
            print("v40.1 修复 E2E v3")
            print("=" * 70)

            # 1. 登录
            print("\n[1] dev-login + 进入主页")
            await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
            await page.goto(f"{BASE_URL}/", wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            # 2. 在浏览器内动态挂载 StepScopeSummary 测试
            print("\n[2] 浏览器内动态挂载测试组件")
            mount_result = await page.evaluate("""async () => {
                try {
                    var app = document.querySelector('#app').__vue_app__;
                    if (!app) return { error: 'no_app' };

                    // 通过 dynamic import 加载 StepScopeSummary 组件
                    var mod = await import('/src/views/AADiagramApp/components/steps/StepScopeSummary.vue');
                    var Comp = mod.default;

                    // 创建测试 div
                    var testDiv = document.createElement('div');
                    testDiv.id = 'test-summary-container';
                    testDiv.style.cssText = 'position:fixed;top:0;left:0;z-index:99999;background:white;padding:20px;width:1200px;';
                    document.body.appendChild(testDiv);

                    // 关键场景: incremental.businessObjects=0 但 objectRelations=4
                    // 通过 app._context.config.globalProperties 拿 vue, 或用 app.runWithContext
                    // 实际上 Vue 3 不暴露 vue 引用, 但 app 内部使用同一个 vue 模块
                    // 解决: 复用 app 的 vue - 通过 app._context.provides 找不到, 用 window 上的 'vue' 别名
                    // Vite dev 通常会暴露模块到 window.__vite_module_cache, 但更直接:
                    // 复用 app: app.mount(testDiv) 但需要改 h 调用
                    // 用 createApp from app: 实际是同一个 Vue
                    var VueRuntime = null;
                    // 方法 1: 通过 app 的 _component 拿到 (私有 API)
                    if (app._context && app._context.appContext) {
                        // appContext.config.globalProperties 通常包含 $vue
                    }
                    // 方法 2: 通过 require 拿 - vite 提供 import.meta.glob 但不直接
                    // 方法 3: 复用现有 vue 路径 - vite alias "@" → "/src"
                    var vueMod = await import('/node_modules/.vite/deps/vue.js?v=any').catch(function() { return null; });
                    if (vueMod && vueMod.createApp) {
                        VueRuntime = vueMod;
                    } else {
                        // 兜底: 通过 fetch 拿到 vue 入口
                        // 不行, 只能复用现有 app
                        // 改用策略: 通过 app.component 注册一个测试组件
                        app.component('TestScopeSummary', Comp);
                        // 然后通过 createApp + use 注入 Component
                        // 实际上用 app 的 component 注册后, 可以在 app 树里渲染
                        // 但我们要独立 mount 一个新 div
                        return { error: 'vue_runtime_not_found' };
                    }

                    var createApp = VueRuntime.createApp;
                    var h = VueRuntime.h;

                    var testApp = createApp({
                        setup() {
                            return () => h(Comp, {
                                center: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 19 },
                                incremental: { domains: 0, subDomains: 0, serviceModules: 0, businessObjects: 0, objectRelations: 4 },
                                total: { domains: 3, subDomains: 6, serviceModules: 12, businessObjects: 18, objectRelations: 23 }
                            });
                        }
                    });
                    testApp.mount(testDiv);
                    await new Promise(function(r) { setTimeout(r, 200); });

                    // 提取数据
                    var incCard = testDiv.querySelector('.summary-card--incremental');
                    var totalCard = testDiv.querySelector('.summary-card--total');
                    var centerCard = testDiv.querySelector('.summary-card--center');

                    var extract = function(card) {
                        if (!card) return null;
                        return {
                            hasEmpty: !!card.querySelector('.summary-card__empty'),
                            emptyText: card.querySelector('.summary-card__empty') ? card.querySelector('.summary-card__empty').textContent.trim() : null,
                            nums: Array.from(card.querySelectorAll('.stat-item__num')).map(function(e) { return e.textContent.trim(); }),
                            lbls: Array.from(card.querySelectorAll('.stat-item__label')).map(function(e) { return e.textContent.trim(); })
                        };
                    };

                    var result = {
                        center: extract(centerCard),
                        incremental: extract(incCard),
                        total: extract(totalCard)
                    };

                    // 清理
                    testApp.unmount();
                    testDiv.remove();

                    return { ok: true, data: result };
                } catch (e) {
                    return { error: e.message, stack: e.stack };
                }
            }""")
            print(f"    -> {mount_result}")

            if mount_result.get('ok'):
                data = mount_result['data']
                print(f"    center: {data['center']}")
                print(f"    incremental: {data['incremental']}")
                print(f"    total: {data['total']}")

                # 关键断言 1: incremental 卡片不显示 —
                inc = data['incremental']
                record("关系范围卡片不再显示 — (v40.1 修复)",
                       inc and not inc['hasEmpty'],
                       f"hasEmpty={inc['hasEmpty'] if inc else None}, nums={inc['nums'] if inc else None}")

                # 关键断言 2: incremental 关系数 = +4
                if inc and inc['nums']:
                    rel_n = inc['nums'][-1]
                    record("关系范围关系数 = +4 (修复后正确显示增量)",
                           rel_n == '+4' or rel_n == '4',
                           f"rel_n={rel_n}")

                # 关键断言 3: 中心 + 增量 = 总数 (闭环)
                if (data['center'] and data['center']['nums'] and
                    data['incremental'] and data['incremental']['nums'] and
                    data['total'] and data['total']['nums']):
                    c = data['center']['nums']
                    i = data['incremental']['nums']
                    t = data['total']['nums']
                    for idx, label in enumerate(['域', '子', '服', '对', '关系']):
                        cn = int(c[idx]) if c[idx].isdigit() else 0
                        iv_str = i[idx].lstrip('+')
                        iv = int(iv_str) if iv_str.isdigit() else 0
                        tn = int(t[idx]) if t[idx].isdigit() else 0
                        ok = cn + iv == tn
                        record(f"闭环: 中心{label}({cn}) + 增量{label}({iv}) = 总数{label}({tn})",
                               ok, "" if ok else f"sum={cn+iv}")
            else:
                record("Vue 动态挂载测试", False, str(mount_result.get('error', 'unknown'))[:200])

        except Exception as e:
            print("\n[!!!] 异常 traceback:")
            traceback.print_exc()
            record("E2E 异常", False, str(e)[:200])
        finally:
            await browser.close()

    print("\n" + "=" * 70)
    print("E2E 验证结果")
    print("=" * 70)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  PASS: {passed}  |  FAIL: {failed}")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[!!!] Main crashed: {e}")
        import traceback
        traceback.print_exc()
