"""
验证修复: disable "供应链云" 领域后图表应更新.

前端在 3006 (Vite proxy → backend 3010).
PlaywrightCLI.authenticated_navigate 默认用 3004, 这里手动导航.
"""
import sys
import time
import json

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3006'
TARGET_PATH = '/system/archdata'


def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()

        # 1. dev-login
        print('[1] dev-login ...')
        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin',
                  wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        # 2. SPA 导航到 /system/archdata (不带 query, 后面手动设版本)
        print('[2] SPA 导航到 /system/archdata ...')
        page.goto(FRONTEND, wait_until='domcontentloaded', timeout=15000)
        page.wait_for_function("""
            () => {
                const app = document.querySelector('#app')?.__vue_app__
                const pinia = app?.config?.globalProperties?.$pinia
                let store = pinia?._s?.get('auth')
                if (!store && window.__pinia) store = window.__pinia._s?.get('auth')
                return !!(store && store.user)
            }
        """, timeout=20000)
        page.evaluate(f"""
            () => {{
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router
                router.push('{TARGET_PATH}')
            }}
        """)

        # 3. 等 window.__archPage.versionContext 可用
        print('[3] 等 __archPage.versionContext 可用 ...')
        page.wait_for_function("""
            () => !!(window.__archPage && window.__archPage.versionContext)
        """, timeout=30000)

        # 4. 找一个有架构数据的版本并选中
        print('[4] 查找并选中有数据的版本 ...')
        pick_result = page.evaluate('''async () => {
            const vc = window.__archPage.versionContext;
            // 拉产品
            if (!vc.products.value || vc.products.value.length === 0) {
                await vc.fetchProducts();
            }
            const products = vc.products.value || [];
            if (!products.length) return { error: 'no products' };

            // 遍历产品+版本, 找有 BO 数据的
            for (const p of products) {
                await vc.selectProduct(p);
                const versions = vc.versions.value || [];
                for (const v of versions) {
                    try {
                        const ar = await fetch(`/api/v2/bo/architecture/preview?version_id=${v.id}`, { credentials: 'include' });
                        const aj = await ar.json();
                        const boCount = aj.data?.business_objects?.length || aj.business_objects?.length || 0;
                        if (boCount >= 5) {
                            vc.selectVersion(v);
                            return { pid: p.id, vid: v.id, pname: p.name, vname: v.name, boCount };
                        }
                    } catch (e) {}
                }
            }
            return { error: 'no version with data' };
        }''')
        print(f'  {pick_result}')
        if pick_result.get('error'):
            print(f'  ERROR: {pick_result["error"]}')
            return

        # 5. 等 versionContext.selectedVersionId 设置 + 图表渲染
        print('[5] 等 versionContext.selectedVersionId 设置 ...')
        page.wait_for_function(f"""
            () => window.__archPage?.versionContext?.selectedVersionId?.value === {pick_result['vid']}
        """, timeout=15000)

        # 6. 切换到图表视图 (先选对象范围, 再点"图表展示"按钮)
        print('[6] 点击"全选"选中对象范围 + 切换图表视图 ...')
        try:
            # 6a. 点"全选"按钮 (对象范围树)
            page.locator('button:has-text("全选")').first.click(timeout=10000)
            print('  已点击全选按钮')
            time.sleep(2)
        except Exception as e:
            print(f'  warn: 点击全选失败: {e}')

        # 6b. 等 canShowChart 变 true
        try:
            page.wait_for_function("""
                () => !!(window.__archPage && window.__archPage.hasScopeSelection && window.__archPage.hasScopeSelection.value)
            """, timeout=15000)
            print('  hasScopeSelection=true')
        except Exception as e:
            print(f'  warn: hasScopeSelection 未变 true: {e}')

        # 6c. 点"图表展示"按钮
        try:
            page.locator('button:has-text("图表展示")').first.click(timeout=10000)
            print('  已点击图表展示按钮')
        except Exception as e:
            print(f'  warn: 点击图表展示失败: {e}, 尝试 evaluate click')
            page.evaluate('''() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.textContent && b.textContent.includes('图表展示')) {
                        b.click();
                        return true;
                    }
                }
                return false;
            }''')

        # 等 EmbeddedChartView chartConfig 写入 (onMounted 暴露 __archPage.chartConfig)
        print('[7] 等 __archPage.chartConfig 可用 + SVG 渲染 ...')
        try:
            page.wait_for_function("""
                () => !!(window.__archPage && window.__archPage.chartConfig)
            """, timeout=20000)
        except Exception as e:
            print(f'  warn: chartConfig 不可用: {e}')

        # 等 SVG 出现
        try:
            page.wait_for_selector('.embedded-chart-view__canvas svg', timeout=90000)
            print('  OK SVG 已出现')
        except Exception as e:
            print(f'  warn: 等 SVG 超时: {e}')
            cli.screenshot('debug_no_svg.png')
            url = page.url
            body_text = page.evaluate('() => document.body.innerText.slice(0, 800)')
            print(f'  current URL: {url}')
            print(f'  body text (first 800): {body_text}')
            return

        try:
            page.wait_for_selector('[data-chart-rendered="true"]', timeout=30000)
        except Exception:
            print('  warn: data-chart-rendered 未设置, 继续')
        # 多等 3s 让 syncLayoutControlFromDiagramData 把 groups 写入 chartConfig
        time.sleep(4)

        # 7. 读取 chartConfig.layoutControl.groups, 列出 domains
        result = page.evaluate('''() => {
            const cfg = window.__archPage && window.__archPage.chartConfig;
            if (!cfg || !cfg.layoutControl || !cfg.layoutControl.groups) {
                return { error: 'chartConfig.layoutControl.groups not ready' };
            }
            const domains = [];
            function collect(items) {
                for (const item of items || []) {
                    if (item.groupType === 'domain' || !item.groupType) {
                        domains.push({ title: item.title, elementCode: item.elementCode, enabled: item.enabled, groupType: item.groupType });
                    }
                    if (item.children) collect(item.children);
                }
            }
            collect(cfg.layoutControl.groups);
            return { domains, groupsCount: cfg.layoutControl.groups.length };
        }''')
        print(f'[7] groups 顶层 count={result.get("groupsCount")}')
        for d in result.get('domains', []):
            print(f'    - title={d["title"]!r}, elementCode={d["elementCode"]!r}, enabled={d["enabled"]}, groupType={d["groupType"]}')

        if 'error' in result:
            print(f'  ERROR: {result["error"]}')
            return

        # 8. 禁用 "供应链云" (跳过截图, 3230 BO 渲染重 full_page 截图超时)
        print('[8] 禁用 "供应链云" ...')

        target = '供应链云'
        print(f'  禁用 {target!r} ...')
        disabled_result = page.evaluate('''(target) => {
            const cfg = window.__archPage && window.__archPage.chartConfig;
            if (!cfg || !cfg.layoutControl || !cfg.layoutControl.groups) {
                return { error: 'no chartConfig' };
            }
            let found = null;
            function traverse(items) {
                for (const item of items || []) {
                    if (item.title === target || item.elementCode === target) {
                        found = item; return true;
                    }
                    if (item.children && traverse(item.children)) return true;
                }
                return false;
            }
            traverse(cfg.layoutControl.groups);
            if (!found) return { error: 'target not found', target };
            const before = { enabled: found.enabled, visible: found.visible };
            found.enabled = false;
            found.visible = false;
            return { before, after: { enabled: found.enabled, visible: found.visible }, title: found.title, elementCode: found.elementCode };
        }''', target)
        print(f'  disabled result: {json.dumps(disabled_result, ensure_ascii=False)}')
        if 'error' in disabled_result:
            print(f'  ERROR: {disabled_result["error"]}')
            return

        # 等 generateDiagram (250ms debounce) + mermaid.run (3230 BO 重绘需要时间)
        print('  等图表重新渲染 ...')
        time.sleep(10)
        try:
            page.wait_for_selector('[data-chart-rendered="true"]', timeout=20000, state='attached')
        except Exception as e:
            print(f'  warn: wait_for_selector: {e}')

        # 9. 验证 SVG 中 "供应链云" 文本
        print('[9] 验证 SVG 中 "供应链云" 文本 ...')

        verify = page.evaluate('''() => {
            const svg = document.querySelector('.embedded-chart-view__canvas svg');
            if (!svg) return { error: 'no svg' };
            const text = svg.textContent || '';
            const count = (text.match(/供应链云/g) || []).length;
            const clusters = svg.querySelectorAll('g.cluster');
            const clusterTexts = Array.from(clusters).map(c => (c.textContent || '').trim().split(/\\n|\\r/)[0]);
            return { count, clusterCount: clusters.length, clusterTexts, svgLength: text.length };
        }''')
        print(f'  verify: {json.dumps(verify, ensure_ascii=False)}')

        if 'error' in verify:
            print(f'  ERROR: {verify["error"]}')
            return

        if verify['count'] == 0:
            print('\n✓ PASS: "供应链云" 已从图表中消失')
        else:
            print(f'\n✗ FAIL: "供应链云" 仍出现 {verify["count"]} 次')
            if any('供应链云' in t for t in verify.get('clusterTexts', [])):
                print(f'  clusterTexts 中仍有: {[t for t in verify["clusterTexts"] if "供应链云" in t]}')

    finally:
        cli.close()


if __name__ == '__main__':
    main()
