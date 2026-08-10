"""
查询各版本 BO 数量 (复用 versionContext 方法), 找适合折叠自测的适中版本.
"""
import sys
import time

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3005'


def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(25000)
        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin',
                  wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)
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
        page.evaluate("""() => {
            const router = document.querySelector('#app').__vue_app__.config.globalProperties.$router;
            router.push('/system/archdata');
        }""")
        page.wait_for_function("""
            () => !!(window.__archPage && window.__archPage.versionContext)
        """, timeout=30000)

        rows = page.evaluate('''async () => {
            const vc = window.__archPage.versionContext;
            if (!vc.products.value || vc.products.value.length === 0) await vc.fetchProducts();
            const products = vc.products.value || [];
            const out = [];
            for (const p of products) {
                await vc.selectProduct(p);
                const versions = vc.versions.value || [];
                for (const v of versions) {
                    try {
                        const r = await fetch(`/api/v2/bo/architecture/preview?version_id=${v.id}`, { credentials: 'include' });
                        const j = await r.json();
                        const boCount = j.data?.business_objects?.length || j.business_objects?.length || 0;
                        out.push({ pid: p.id, pname: p.name, vid: v.id, vname: v.version_code || v.name || v.code, boCount });
                    } catch (e) {}
                }
            }
            return out;
        }''')
        rows = sorted(rows, key=lambda x: x['boCount'])
        print('versions (by boCount asc):')
        for r in rows[:50]:
            print(f'  vid={r["vid"]} boCount={r["boCount"]} pname={r["pname"]!r} vname={r["vname"]!r}')
        print('  ...')
        for r in rows[-10:]:
            print(f'  vid={r["vid"]} boCount={r["boCount"]} pname={r["pname"]!r} vname={r["vname"]!r}')
    finally:
        cli.close()


if __name__ == '__main__':
    main()