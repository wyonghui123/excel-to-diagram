"""
_verify_scope_data.py - 确认排查/验证采用数据的对象范围

用户要求: 采用数据范围 = 供应链云领域下的 供应链计划 子领域
本脚本通过后端 API 核对:
  1. sub_domain id=299 是否为 供应链计划, 其 domain_id 是否指向 供应链云
  2. _diag_bo_switch.py 使用的 business_object ids 是否全部属于 sub_domain 299
  3. 供应链计划子领域的 BO 数量 / 供应链云领域下的子领域清单
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3005'
VERSION_ID = 863

# _diag_bo_switch.py 中用的 BO id 列表
DIAG_BO_IDS = [3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
               2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
               2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787]

FETCH_JS = """(async () => {
    const base = '/api/v2/bo/'
    const q = (type, params) => {
        const qs = new URLSearchParams(params).toString()
        return fetch(base + type + '?' + qs).then(r => r.json())
    }
    const page = 1000
    const [subRes, domRes] = await Promise.all([
        q('sub_domain', { version_id: VERSION, page_size: 5000 }),
        q('domain', { version_id: VERSION, page_size: 1000 }),
    ])
    const subs = (subRes.data?.items || subRes.data || [])
    const doms = (domRes.data?.items || domRes.data || [])
    const gyl = subs.find(s => (s.name || '').includes('供应链计划'))
    const dom = gyl ? doms.find(d => d.id === gyl.domain_id) : null
    // 该子领域下所有 BO
    let boCount = 0, boInScope = [], boNotInScope = []
    if (gyl) {
        const boRes = await q('business_object', { version_id: VERSION, page_size: 5000, sub_domain_id: gyl.id })
        const bos = (boRes.data?.items || boRes.data || [])
        boCount = bos.length
        const idSet = new Set(bos.map(b => b.id))
        boInScope = DIAG_BO_IDS.filter(id => idSet.has(id))
        boNotInScope = DIAG_BO_IDS.filter(id => !idSet.has(id))
    }
    // 供应链云领域下所有子领域
    const cloudDom = doms.find(d => (d.name || '').includes('供应链云'))
    const cloudSubs = cloudDom ? subs.filter(s => s.domain_id === cloudDom.id).map(s => ({ id: s.id, name: s.name })) : []
    return {
        target: gyl ? { id: gyl.id, code: gyl.code, name: gyl.name, domain_id: gyl.domain_id } : null,
        domain: dom ? { id: dom.id, code: dom.code, name: dom.name } : null,
        cloudDomain: cloudDom ? { id: cloudDom.id, code: cloudDom.code, name: cloudDom.name } : null,
        cloudSubs,
        boCount,
        boInScope,
        boNotInScope,
        totalDomains: doms.length,
        totalSubs: subs.length,
    }
})()"""


def main():
    with PlaywrightCLI(headless=True) as cli:
        print('[v] 1 dev-login', flush=True)
        cli.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
        cli.wait_for_timeout(1500)

        print('[v] 2 查询后端数据', flush=True)
        js = FETCH_JS \
            .replace('VERSION', str(VERSION_ID)) \
            .replace('DIAG_BO_IDS', json.dumps(DIAG_BO_IDS))
        r = cli.evaluate_async(js, timeout=60000)
        print(json.dumps(r, ensure_ascii=False, indent=2), flush=True)

        print('\n========== 结论 ==========', flush=True)
        if r.get('target') and r.get('domain'):
            match = r['target']['name'] == '供应链计划' and (r['domain']['name'] or '').find('供应链云') != -1
            print(f'sub_domain 299 判定: {"✅ 是 供应链计划 / 供应链云" if match else "❌ 不符合"}', flush=True)
            print(f'  实际: sub_domain id={r["target"]["id"]} name={r["target"]["name"]} '
                  f'domain_id={r["target"]["domain_id"]} domain={r["domain"]["name"]}', flush=True)
        else:
            print('⚠️ 未找到 供应链计划 子领域', flush=True)

        if r.get('boInScope') is not None:
            total = len(DIAG_BO_IDS)
            ins = len(r['boInScope'])
            print(f'_diag_bo_switch.py 的 {total} 个 BO id: {ins} 个属于该子领域, '
                  f'{total - ins} 个不属于 (见 boNotInScope)', flush=True)
        print(f'供应链计划 子领域 BO 总数: {r.get("boCount")}', flush=True)


if __name__ == '__main__':
    main()
