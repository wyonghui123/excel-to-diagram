"""
查询 vid=863 的 domain 与 sub_domain, 定位 供应链云 和 供应链计划 的 id.
"""
import sys
import time

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = 'http://localhost:3005'
VID = 863


def main():
    cli = PlaywrightCLI(headless=True)
    try:
        page = cli._ensure_browser()
        page.set_default_timeout(25000)
        page.goto(f'{FRONTEND}/api/v1/auth/dev-login?username=admin',
                  wait_until='domcontentloaded', timeout=15000)
        time.sleep(1)

        res = page.evaluate('''async (vid) => {
            const d = await (await fetch(`/api/v2/bo/domain?version_id=${vid}&page_size=1000`, { credentials: 'include' })).json();
            const s = await (await fetch(`/api/v2/bo/sub_domain?version_id=${vid}&page_size=1000`, { credentials: 'include' })).json();
            const domains = d.data?.items || d.data || [];
            const subDomains = s.data?.items || s.data || [];
            return {
                domains: domains.map(x => ({ id: x.id, name: x.name, code: x.code, element_code: x.element_code })),
                subDomains: subDomains.map(x => ({ id: x.id, domain_id: x.domain_id, name: x.name, code: x.code, element_code: x.element_code }))
            };
        }''', VID)
        print('=== domains ===')
        for x in res['domains']:
            mark = '  <-- 供应链云' if x['name'] == '供应链云' else ''
            print(f'  id={x["id"]} name={x["name"]!r} code={x["code"]!r}{mark}')
        print('=== sub_domains (供应链 相关) ===')
        for x in res['subDomains']:
            if '链' in (x['name'] or '') or '计划' in (x['name'] or ''):
                print(f'  id={x["id"]} domain_id={x["domain_id"]} name={x["name"]!r} code={x["code"]!r}')
    finally:
        cli.close()


if __name__ == '__main__':
    main()