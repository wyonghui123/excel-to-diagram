# -*- coding: utf-8 -*-
"""[Spec 19 FR-014 伴随] 批量清理维度范围失效引用（PM 已授权 2026-09-06）

背景：35 条 permission_set_dimension_scopes 引用已删除对象（domains id 5-18 等测试
清理产物），后端名称富化 miss → 前端 chip 显示裸 ID。PM 授权批量清理。

流程：
  1. 只读 SQLite 检测失效 (ps_id, dimension_code, stale_ids)（不写库）
  2. 每个涉事 PS：GET 当前 scopes → 备份 JSON → 剔除失效 id（整行清空则丢弃该行）
     → POST 正规写路径回写（复用 _normalize_dim_values_to_ids 规范化）
  3. 复验：GET 回读断言无失效引用残留、有效行未动（PS 1198）

用法：python -I scripts/cleanup_stale_dim_refs.py [--dry-run]
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import requests

BASE = 'http://127.0.0.1:3011'
ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / 'meta' / 'architecture.db'
BACKUP_DIR = ROOT / 'test_output'

DRY_RUN = '--dry-run' in sys.argv


def detect_stale():
    """只读检测：返回 {ps_id: [(dimension_code, values, scope_mode, inherit, stale_ids), ...]}"""
    con = sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True)
    cur = con.cursor()
    rows = cur.execute(
        'SELECT permission_set_id, dimension_code, dimension_values, scope_mode, inherit_children '
        'FROM permission_set_dimension_scopes').fetchall()
    con.close()

    def missing(table, ids):
        q = ','.join('?' * len(ids))
        got = {r[0] for r in con_cur(table, q, ids)}
        return [i for i in ids if i not in got]

    def con_cur(table, q, ids):
        c = sqlite3.connect(f'file:{DB.as_posix()}?mode=ro', uri=True).cursor()
        return c.execute(f'SELECT id FROM {table} WHERE id IN ({q})', ids).fetchall()

    plan = {}
    for ps, code, raw, mode, inherit in rows:
        try:
            vals = json.loads(raw or '[]')
        except (json.JSONDecodeError, TypeError):
            continue
        if not vals or vals == ['*']:
            continue  # 通配符/空值不处理
        ids = [v for v in vals if isinstance(v, int)]
        if not ids:
            continue
        table = code if code.endswith('s') else code + 's'
        stale = missing(table, ids)
        if stale:
            plan.setdefault(ps, []).append((code, vals, mode, inherit, stale))
    return plan


def main():
    plan = detect_stale()
    total_stale = sum(len(item[4]) for items in plan.values() for item in items)
    print(f'检测到 {len(plan)} 个 PS / {total_stale} 个失效引用')
    for ps, items in plan.items():
        for code, vals, mode, inherit, stale in items:
            print(f'  PS {ps} {code} {vals} mode={mode} → 失效 {stale}')

    if DRY_RUN:
        print('\n[dry-run] 未执行清理')
        return

    s = requests.Session()
    r = s.get(BASE + '/api/v1/auth/dev-login', params={'username': 'admin'}, timeout=8)
    assert r.status_code == 200, f'dev-login 失败: {r.status_code}'

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = {}
    cleaned = 0
    for ps, items in plan.items():
        r = s.get(f'{BASE}/api/v1/permission-sets/{ps}/dimension-scopes', timeout=8)
        r.raise_for_status()
        data = r.json().get('data') or []
        backup[str(ps)] = data  # 全量备份（富化后的形态）

        stale_map = {code: set(stale) for code, _, _, _, stale in items}
        body = []
        for scope in data:
            code = scope.get('dimension_code')
            vals = scope.get('dimension_values') or []
            ids = [v['id'] if isinstance(v, dict) else v for v in vals]
            if vals == ['*'] or (vals and vals[0] == '*'):
                body.append(_strip(scope))  # 通配符原样保留
                continue
            keep = [i for i in ids if i not in stale_map.get(code, set())]
            if not keep:
                continue  # 整行清空 → 丢弃该行（等价「未配置」）
            scope['dimension_values'] = keep
            body.append(_strip(scope))

        r2 = s.post(f'{BASE}/api/v1/permission-sets/{ps}/dimension-scopes', json=body, timeout=8)
        ok = r2.status_code == 200 and r2.json().get('success')
        print(f'PS {ps} 回写: {"OK" if ok else "FAIL " + r2.text[:200]}')
        cleaned += 1 if ok else 0

    (BACKUP_DIR / f'stale_dim_refs_backup_{ts}.json').write_text(
        json.dumps(backup, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'\n备份: stale_dim_refs_backup_{ts}.json | 回写成功 {cleaned}/{len(plan)} PS')

    # 复验
    plan2 = detect_stale()
    remain = sum(len(item[4]) for items in plan2.values() for item in items)
    # 有效行回归（PS 1198 sub_domain 64 必须仍在）
    r3 = s.get(f'{BASE}/api/v1/permission-sets/1198/dimension-scopes', timeout=8)
    valid_kept = any(
        any((v.get('id') == 64) if isinstance(v, dict) else v == 64
            for v in (it.get('dimension_values') or []))
        for it in (r3.json().get('data') or []))
    print(f'复验: 失效引用残留 {remain} | 有效行(1198/64)保留: {valid_kept}')
    sys.exit(0 if remain == 0 and valid_kept else 1)


def _strip(scope):
    """GET 富化形态 → POST 最小字段"""
    return {
        'dimension_code': scope.get('dimension_code'),
        'dimension_values': scope.get('dimension_values') or [],
        'inherit_children': scope.get('inherit_children'),
        'scope_mode': scope.get('scope_mode') or 'include',
    }


if __name__ == '__main__':
    main()
