"""
scenario.py - 图表调试场景搭建器
======================================================================
[目的] 消除"复现 bug 前搭建环境"的手工开销:
  每次排查都要: 查 DB 找 sub_domain/domain id → 调后端 API 分页拉关系
  → 手工拼 base64 scope URL. 本模块一键完成.

[用法]
  # 1) 一键拿到命名场景 URL (已含 dev-login 前置, 直接用 shortcut 打开)
  python -c "from test_helpers import scenario as sc; print(sc.get_scenario_url('mm-cross-domain'))"

  # 2) 任意 sub_domain + 关系模式
  from test_helpers import scenario as sc
  url = sc.build_url(sub_domain='MM', relation_mode='all_cross_domain')

  # 3) 编程取 scope dict (供 ChartDiag.open_chart / ScenarioRunner 使用)
  scope = sc.scope_dict(sub_domain='MM', relation_mode='all_cross_domain')

[关系模式 relation_mode]
  - 'all_cross_domain': sub_domain 到所有外部领域的关系 (用户"范围外部跨领域")
  - 'to_domain':        仅到指定 domain (传 target_domain='FIN'/'PROC'...)
  - 'specific':         调用方直接给 relation_ids
  - 'none':             不含关系 (等同 scopeCode 仅对象范围)

[依赖]
  - meta/architecture.db (domains/sub_domains/business_objects)
  - 后端 3010 关系接口 (/api/v2/bo/relationship, 分页拉取)
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import urllib.request
import http.cookiejar
from pathlib import Path
from typing import Dict, List, Optional

from test_helpers.env_preflight import FRONTEND_URL, BACKEND_URL

# ---- 环境常量 (TTTTT000 / V11) ----
PRODUCT_CODE = 'TTTTT000'
VERSION_CODE = 'V11'
VERSION_ID = 863
REPO_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = REPO_ROOT / 'meta' / 'architecture.db'
CACHE_DIR = REPO_ROOT / 'test_helpers'

# ---- 命名场景 ----
# 值: dict(scope 构建参数) 或 dict(use_scope_code=编码) (走简洁 scopeCode 路径)
SCENARIOS = {
    # 用户核心场景: 采购供应 + 所有跨领域关系 (2026-08-14 ELK 系统分组 bug 复现场景)
    'mm-cross-domain': dict(sub_domain='MM', relation_mode='all_cross_domain'),
    # 标准测试范围: 供应链计划(SCP) 约30 BO, 不加载全量 (效率铁律)
    'scp': dict(use_scope_code='SCP'),
    # 采购供应 + 跨到采购云(PROC)
    'mm-proc': dict(sub_domain='MM', relation_mode='to_domain', target_domain='PROC'),
    # 采购供应 + 跨到财务云(FIN)
    'mm-fin': dict(sub_domain='MM', relation_mode='to_domain', target_domain='FIN'),
    # 采购供应 + 跨到项目云(PM/PRJ)
    'mm-prj': dict(sub_domain='MM', relation_mode='to_domain', target_domain='PRJ'),
}


# ---------------------------------------------------------------
# DB 查询
# ---------------------------------------------------------------
def _db():
    if not DB_PATH.exists():
        raise FileNotFoundError(f'架构 DB 不存在: {DB_PATH}')
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_sub_domain(code: str, version_id: int = VERSION_ID) -> Optional[dict]:
    with _db() as c:
        r = c.execute(
            'SELECT * FROM sub_domains WHERE code=? AND version_id=?', (code, version_id)
        ).fetchone()
        return dict(r) if r else None


def get_domain(code: str, version_id: int = VERSION_ID) -> Optional[dict]:
    with _db() as c:
        r = c.execute(
            'SELECT * FROM domains WHERE code=? AND version_id=?', (code, version_id)
        ).fetchone()
        return dict(r) if r else None


def get_bo_ids_in_sub_domain(sub_domain_id: int, version_id: int = VERSION_ID) -> Dict[int, str]:
    """sub_domain 下所有 BO: {bo_id: bo_code}."""
    with _db() as c:
        rows = c.execute(
            'SELECT id, code FROM business_objects WHERE version_id=? AND sub_domain_id=?',
            (version_id, sub_domain_id),
        ).fetchall()
        return {r['id']: r['code'] for r in rows}


# ---------------------------------------------------------------
# 后端关系拉取
# ---------------------------------------------------------------
def fetch_relations(version_id: int = VERSION_ID, base_url: str = BACKEND_URL) -> List[dict]:
    """分页拉取全部关系 (后端 3010). 自动 dev-login 设 cookie."""
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.open(f'{base_url}/api/v1/auth/dev-login?username=admin', timeout=30)
    rels: List[dict] = []
    page = 1
    while True:
        req = urllib.request.Request(
            f'{base_url}/api/v2/bo/relationship?version_id={version_id}&page={page}&page_size=500'
        )
        with opener.open(req, timeout=120) as r:
            data = json.loads(r.read().decode('utf-8'))
        inner = data.get('data') if isinstance(data, dict) else None
        batch = inner.get('items') if isinstance(inner, dict) else (data if isinstance(data, list) else [])
        if not batch:
            break
        rels.extend(batch)
        if len(batch) < 500 or page > 30:
            break
        page += 1
    return rels


# ---------------------------------------------------------------
# 关系 id 计算 + 缓存
# ---------------------------------------------------------------
def _cache_path(key: str) -> Path:
    return CACHE_DIR / f'.cache_{key}_relids.json'


def cross_domain_relation_ids(
    sub_domain_id: int,
    version_id: int = VERSION_ID,
    target_domain_id: Optional[int] = None,
    use_cache: bool = True,
) -> List[int]:
    """sub_domain 的关系 id 列表.
    target_domain_id 为空 → 该 sub_domain 到所有外部领域的关系 (跨领域);
    target_domain_id 给定 → 仅到该领域的关系.
    缓存到 test_helpers/.cache_<sub_domain>[_<target>]_relids.json.
    """
    sd = {r['id']: r['code'] for r in (_db().execute(
        'SELECT id, code FROM business_objects WHERE version_id=? AND sub_domain_id=?',
        (version_id, sub_domain_id)).fetchall())}
    if not sd:
        return []
    sub = _db().execute('SELECT domain_id FROM sub_domains WHERE id=?', (sub_domain_id,)).fetchone()
    own_domain_id = sub['domain_id'] if sub else None

    cache_key = f'sd{sub_domain_id}'
    if target_domain_id:
        cache_key += f'_d{target_domain_id}'
    cache = _cache_path(cache_key)
    if use_cache and cache.exists():
        try:
            return json.loads(cache.read_text(encoding='utf-8'))
        except Exception:
            pass

    rels = fetch_relations(version_id)
    ids: List[int] = []
    for rel in rels:
        if rel.get('id') is None:
            continue
        sbid, tbid = rel.get('source_bo_id'), rel.get('target_bo_id')
        sdd, tdd = rel.get('source_domain_id'), rel.get('target_domain_id')
        # 一端在 sub_domain
        if sbid in sd:
            other_domain = tdd
        elif tbid in sd:
            other_domain = sdd
        else:
            continue
        # 跨领域: 另一端领域 != 自身领域; 若指定 target_domain 则仅匹配该领域
        if other_domain == own_domain_id:
            continue
        if target_domain_id is not None and other_domain != target_domain_id:
            continue
        ids.append(rel['id'])
    ids = list(dict.fromkeys(ids))
    if use_cache:
        CACHE_DIR.mkdir(exist_ok=True)
        cache.write_text(json.dumps(ids), encoding='utf-8')
    return ids


# ---------------------------------------------------------------
# scope dict / URL 构造
# ---------------------------------------------------------------
def scope_dict(
    sub_domain: Optional[str] = None,
    domain: Optional[str] = None,
    relation_mode: str = 'all_cross_domain',
    relation_ids: Optional[List[int]] = None,
    target_domain: Optional[str] = None,
    version_id: int = VERSION_ID,
) -> dict:
    """构造 scope dict (供 shortcut URL / ChartDiag.open_chart / ScenarioRunner)."""
    scope: dict = {'sub_domain': [], 'business_object': [], 'service_module': [], 'domain': []}
    if sub_domain:
        row = get_sub_domain(sub_domain, version_id)
        if not row:
            raise ValueError(f'sub_domain 编码未找到: {sub_domain} (version_id={version_id})')
        scope['sub_domain'] = [row['id']]
    if domain:
        row = get_domain(domain, version_id)
        if not row:
            raise ValueError(f'domain 编码未找到: {domain} (version_id={version_id})')
        scope['domain'] = [row['id']]

    if relation_mode == 'none':
        scope['relation_ids'] = []
    elif relation_mode == 'specific':
        scope['relation_ids'] = list(relation_ids or [])
    else:
        if not scope['sub_domain']:
            raise ValueError('跨领域关系需要 sub_domain 作为对象范围')
        sd_id = scope['sub_domain'][0]
        tgt = get_domain(target_domain, version_id)['id'] if target_domain else None
        scope['relation_ids'] = cross_domain_relation_ids(sd_id, version_id, tgt)
    return scope


def build_url(
    sub_domain: Optional[str] = None,
    domain: Optional[str] = None,
    relation_mode: str = 'all_cross_domain',
    relation_ids: Optional[List[int]] = None,
    target_domain: Optional[str] = None,
    product_code: str = PRODUCT_CODE,
    version_code: str = VERSION_CODE,
    view: str = 'chart',
    mode: str = 'debug',
    base_url: str = FRONTEND_URL,
) -> str:
    """一键生成直达图表视图 URL (含 base64 scope)."""
    scope = scope_dict(sub_domain=sub_domain, domain=domain, relation_mode=relation_mode,
                       relation_ids=relation_ids, target_domain=target_domain)
    scope_b64 = base64.b64encode(json.dumps(scope).encode('utf-8')).decode('ascii')
    return (f'{base_url}/system/archdata?productCode={product_code}&versionCode={version_code}'
            f'&view={view}&mode={mode}&scope={scope_b64}')


def get_scenario_url(name: str, base_url: str = FRONTEND_URL) -> str:
    """按命名场景取 URL (支持 scopeCode 快捷路径)."""
    if name not in SCENARIOS:
        raise KeyError(f'未知场景 {name}, 可用: {list(SCENARIOS)}')
    spec = SCENARIOS[name]
    if 'use_scope_code' in spec:
        return (f'{base_url}/system/archdata?productCode={PRODUCT_CODE}&versionCode={VERSION_CODE}'
                f'&view=chart&mode=debug&scopeCode={spec["use_scope_code"]}')
    return build_url(**spec, base_url=base_url)


def scope_dict_for_scenario(name: str) -> dict:
    """按命名场景取 scope dict (不含 use_scope_code 场景)."""
    spec = SCENARIOS[name]
    if 'use_scope_code' in spec:
        raise ValueError(f'场景 {name} 走 scopeCode 快捷路径, 无 scope dict; 用 get_scenario_url')
    return scope_dict(**spec)


def list_scenarios() -> str:
    return '\n'.join(f'  {k}: {json.dumps(v, ensure_ascii=False)}' for k, v in SCENARIOS.items())
