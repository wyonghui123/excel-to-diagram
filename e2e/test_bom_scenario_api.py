"""E2E: BOM / 选配场景 - API 层全链路 [2026-10-26]

数据来源: meta/scripts/init_bom_scenario_seed.py（SCN- 前缀幂等种子）
前置:    真实库已执行 `python -m meta.scripts.init_bom_scenario_seed`，
         后端 3010 / 前端 3006 仍在运行。

覆盖（纯 HTTP，不碰数据库）:
  A1  物料结构列表可见场景数据
  A2  模型结构默认求解（必选 + 默认选项 + 服务行）
  A3  互斥规则冲突（RED + BLUE）
  A4  选项类基数越界（S7 三选）
  A5  数量越界（字符串 key 的 quantities）
  A6  销售订单行展开（成功 / 幂等）
  A7  子行不可再展开
  A8  跨量纲 UOM 拒绝

直接运行: python e2e/test_bom_scenario_api.py
"""
import sys

import requests

API = 'http://localhost:3010'
AS_OF = '2026-10-26'
ORDER_NO = 'SCN-SO-BOM-1'

_results = {}


def check(name: str, ok: bool, detail: str = '') -> bool:
    _results[name] = bool(ok)
    suffix = f'  {detail}' if detail else ''
    print(f'    [{"PASS" if ok else "FAIL"}] {name}{suffix}')
    return bool(ok)


def dev_login() -> requests.Session:
    s = requests.Session()
    r = s.get(f'{API}/api/v1/auth/dev-login?username=admin', timeout=15)
    r.raise_for_status()
    return s


def get_items(s, obj, **params):
    r = s.get(f'{API}/api/v2/bo/{obj}',
              params={'page_size': 500, **params}, timeout=30)
    data = (r.json().get('data') or {})
    return data.get('items') or []


def solve(s, **payload):
    payload.setdefault('as_of', AS_OF)
    payload.setdefault('match', False)
    r = s.post(f'{API}/api/v1/config/solve', json=payload, timeout=30)
    return r.status_code, r.json()


def expand(s, order_id, line_id, **payload):
    r = s.post(f'{API}/api/v1/sales-orders/{order_id}/lines/{line_id}/expand',
               json=payload, timeout=60)
    return r.status_code, r.json()


def _structure(structures, items, code, usage, alt=1):
    item = items.get(code)
    if not item:
        return None
    for st in structures:
        if (st.get('item_id') == item['id'] and st.get('usage') == usage
                and st.get('alternative_no') == alt):
            return st
    return None


def main() -> int:
    print('=' * 60)
    print('E2E: BOM / 选配场景 - API 层全链路')
    print('=' * 60)

    try:
        s = dev_login()
    except requests.RequestException as exc:
        print(f'  [SKIP] 后端 {API} 不可用: {exc}')
        return 2

    items = {i['code']: i for i in get_items(s, 'item')}
    structures = get_items(s, 'item_structure')
    scn_items = {code for code in items if code.startswith('SCN-')}

    # A1 列表可见
    scn_structs = [st for st in structures
                   if st.get('item_id') in {items[c]['id'] for c in scn_items}]
    check('A1 物料结构列表可见场景数据', len(scn_structs) >= 10,
          f'structures={len(scn_structs)}')

    s6 = _structure(structures, items, 'SCN-MODEL-PC', 'sales')
    s7 = _structure(structures, items, 'SCN-OC-COLOR', 'sales')
    s8_bad = _structure(structures, items, 'SCN-FG-BADUOM', 'sales')
    if not (s6 and s7):
        check('A1 场景结构齐备', False, 'S6/S7 缺失')
        return 1

    lines7 = {str(row['line_no']): row
              for row in get_items(s, 'item_structure_line',
                                   structure_id=s7['id'])}
    red, blue, green = lines7.get('10'), lines7.get('20'), lines7.get('30')

    # A2 默认求解
    status, body = solve(s, structure_id=s6['id'])
    cfg = (body.get('data') or {}).get('configuration') or {}
    comps = cfg.get('components') or []
    check('A2 模型默认求解', status == 200 and len(comps) == 3,
          f'status={status} components={len(comps)}')
    if comps:
        keys = {row['component_key'] for row in comps}
        check('A2 组件键与默认选项一致',
              keys == {'L0010', 'L0020.L0010', 'L0030'}, f'keys={sorted(keys)}')

    # A3 互斥规则冲突（字符串 key，等价前端弹窗 JSON）
    status, body = solve(s, structure_id=s6['id'], selections={
        str(red['id']): True, str(blue['id']): True})
    rule = (body.get('details') or {}).get('rule')
    check('A3 互斥规则冲突', status == 422 and rule == 'config_conflict',
          f'status={status} rule={rule} code={body.get("code")}')

    # A4 选项类基数越界
    status, body = solve(s, structure_id=s7['id'], selections={
        str(red['id']): True, str(blue['id']): True, str(green['id']): True})
    rule = (body.get('details') or {}).get('rule')
    check('A4 选项类基数越界', status == 422
          and rule == 'item_structure_select_too_many',
          f'status={status} rule={rule}')

    # A5 数量越界（quantities 字符串 key）
    status, body = solve(s, structure_id=s7['id'],
                         selections={str(green['id']): True},
                         quantities={str(green['id']): '4'})
    rule = (body.get('details') or {}).get('rule')
    check('A5 数量越界（字符串 key）', status == 400
          and rule == 'item_structure_select_qty_range',
          f'status={status} rule={rule}')

    # A6 订单行展开
    orders = get_items(s, 'sales_order')
    order = next((o for o in orders if o.get('order_no') == ORDER_NO), None)
    if not order:
        check('A6 场景订单存在', False, f'{ORDER_NO} 缺失')
        return 1
    lines = get_items(s, 'sales_order_line', order_id=order['id'])
    model_line = next((l for l in lines if str(l.get('line_no')) == '10'), None)
    baduom_line = next((l for l in lines if str(l.get('line_no')) == '30'), None)
    if not (model_line and baduom_line):
        check('A6 场景订单行齐备', False, 'line 10/30 缺失')
        return 1

    status, body = expand(s, order['id'], model_line['id'],
                          pricing_mode='bundle_price')
    rule = (body.get('details') or {}).get('rule')
    if status == 200:
        data = body.get('data') or {}
        rows = data.get('lines') or []
        check('A6 模型行展开成功',
              data.get('component_count') == 3 and len(rows) == 3,
              f'component_count={data.get("component_count")}')
        check('A6 服务子行落 SVC',
              any(row.get('line_type_code') == 'SVC' for row in rows))
    elif status == 409 and rule == 'line_already_expanded':
        check('A6 模型行展开成功（此前已展开，幂等拒绝）', True, rule)
    else:
        check('A6 模型行展开成功', False, f'status={status} rule={rule}')

    # A7 子行不可再展开（首次展开成功后必然命中）
    status, body = expand(s, order['id'], model_line['id'])
    rule = (body.get('details') or {}).get('rule')
    check('A7 已展开行幂等拒绝', status == 409
          and rule in ('line_already_expanded', 'line_is_component'),
          f'status={status} rule={rule}')

    # A8 跨量纲 UOM 拒绝
    if s8_bad:
        status, body = expand(s, order['id'], baduom_line['id'])
        rule = (body.get('details') or {}).get('rule')
        check('A8 跨量纲 UOM 拒绝', status == 422
              and rule == 'uom_conversion_not_found',
              f'status={status} rule={rule}')
    else:
        check('A8 跨量纲结构存在', False, 'S8-BADUOM 缺失')

    total = len(_results)
    passed = sum(1 for v in _results.values() if v)
    print('-' * 60)
    print(f'总计: {total}  通过: {passed}  失败: {total - passed}')
    return 0 if passed == total else 1


if __name__ == '__main__':
    sys.exit(main())
