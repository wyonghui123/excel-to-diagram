"""
chart_seed.py - 图表 E2E 通用种子数据工具 (数据资产化)
======================================================

[核心理念]
  测试数据 = 资产 (seed manifest)，不是 DB 里碰巧存在的数据。
  一套确定性种子 (BO + 关系 + SM，覆盖四类 category) 同时驱动:
    数据完整性 / 颜色 / 备注 / 交互 四维校验 + 问题重现与回归。

[语义种子 2026-08-02] 为什么用 target_code 而不是 target_id
  target_id (如 3220/898/384) 是环境绑定 ID，换版本/产品全部失效。
  target_code (如 DP01/PLA001-PLD00201/DP) 是业务语义，跨环境稳定。
  注入流程: preview 数据 → code 解析出 id → POST 注入。
  → seed manifest 从此与具体环境解耦, 换环境只需 code 存在即可复用。

[数据链路]
  POST /api/v1/annotations (dev-login cookie) → annotations 表
  → preview API (aggregate_annotations_for_targets) → 前端 panel 渲染

[用法]
  python -m test_helpers.chart_seed --probe           # 探测候选目标 (BO/关系/SM)
  python -m test_helpers.chart_seed --inject          # 幂等注入默认清单
  python -m test_helpers.chart_seed --inject --seed-manifest custom.json
  python -m test_helpers.chart_seed --status          # 列出已注入种子
  python -m test_helpers.chart_seed --cleanup         # 按 [E2E-SEED] 前缀清理

[安全]
  - 所有种子 content 带 [E2E-SEED] 前缀，清理只删该前缀，不碰用户真实备注
  - 幂等: 注入前按 (target_type, target_id, content) 查重，已存在则跳过
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Dict, List, Any, Optional

# 与 chart_fixtures.py / chart_diag.py 一致 (当前 vite dev server 端口)
BASE_URL = 'http://localhost:3006'
PRODUCT_CODE = 'TTTTT000'
VERSION_ID = 863

# 种子备注内容统一前缀 (清理安全边界 + 可识别)
SEED_PREFIX = '[E2E-SEED]'

# ── 语义种子清单 (2026-08-02 重构) ──────────────────────────────────
#   用 target_code (业务 code) 定位，不用 target_id (环境 ID)。
#   注入时由 SeedClient.resolve_targets() 通过 preview 数据解析 id。
#   已验证的 code 映射 (版本 863 / 子域 299):
#     BO: DP01=需求计划(1636) 中心节点 / SCN03=位置(3220) / SCN10=供应网络管理方案(3221)
#     REL: PLA001-PLD00201(898) / PLA001-PLD00204(899) (source/target 都在 scope 内, 图表必有连线)
#     SM: DP=需求计划(384, sub_domain_id=299)
DEFAULT_SEEDS: List[Dict[str, Any]] = [
    # ── BO: 中心节点 DP01 双类别 (C 类过滤断言需要同目标多类别) ──
    {'target_type': 'business_object', 'target_code': 'DP01', 'category': 'important',
     'content': '[E2E-SEED] DP01 主流程校验点：中心节点重要备注 (important)'},
    {'target_type': 'business_object', 'target_code': 'DP01', 'category': 'info',
     'content': '[E2E-SEED] DP01 常规信息备注：需求计划核心 (info)'},
    # ── BO: 其他目标补 category 覆盖 ──
    {'target_type': 'business_object', 'target_code': 'SCN03', 'category': 'warning',
     'content': '[E2E-SEED] SCN03 告警备注：数据源异常提示 (warning)'},
    {'target_type': 'business_object', 'target_code': 'SCN10', 'category': 'tip',
     'content': '[E2E-SEED] SCN10 提示备注：建议关注字段 (tip)'},
    # ── 关系: 连线备注 (图表链路) ──
    {'target_type': 'relationship', 'target_code': 'PLA001-PLD00201', 'category': 'warning',
     'content': '[E2E-SEED] 关系 PLA001-PLD00201 链路告警 (warning)'},
    {'target_type': 'relationship', 'target_code': 'PLA001-PLD00204', 'category': 'info',
     'content': '[E2E-SEED] 关系 PLA001-PLD00204 链路信息 (info)'},
    # ── SM: 服务模块备注 (SM 图场景) ──
    {'target_type': 'service_module', 'target_code': 'DP', 'category': 'tip',
     'content': '[E2E-SEED] SM DP 需求计划模块使用提示 (tip)'},
]


class SeedClient:
    """种子数据 HTTP 客户端: dev-login cookie → preview/by-target/create/delete.

    纯 HTTP (urllib + cookiejar)，无需启动浏览器，注入/清理/状态查询秒级完成。
    """

    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip('/')
        self._cj = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._preview_cache: Optional[Dict[str, Any]] = None
        self._login()

    # ── HTTP 基础 ──
    def _req(self, path: str, method: str = 'GET',
             data: Optional[dict] = None) -> Dict[str, Any]:
        url = f'{self.base_url}{path}'
        headers = {'Content-Type': 'application/json'}
        body = None
        if data is not None:
            body = json.dumps(data).encode('utf-8')
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with self._opener.open(req, timeout=30) as resp:
                content = resp.read().decode('utf-8')
                return json.loads(content) if content else {'success': True}
        except urllib.error.HTTPError as e:
            return {'success': False, 'error': f'HTTP {e.code}: {e.read().decode("utf-8", "ignore")[:200]}'}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    def _login(self) -> None:
        """dev-login 设 cookie (Vite proxy 转发到后端)."""
        r = self._req(f'/api/v1/auth/dev-login?username=admin')
        if 'error' in r or r.get('success') is False:
            raise RuntimeError(f'dev-login 失败: {r.get("error", r)}')
        print(f'[chart_seed] dev-login OK (cookies: {len(self._cj)})')

    # ── 数据探测 ──
    def preview(self) -> Dict[str, Any]:
        """拉取 architecture preview (版本 863), 缓存复用."""
        if self._preview_cache is None:
            r = self._req(f'/api/v2/bo/architecture/preview?version_id={VERSION_ID}'
                          f'&product_code={urllib.parse.quote(PRODUCT_CODE)}')
            if not r.get('success'):
                raise RuntimeError(f'preview 拉取失败: {r.get("error", r)}')
            self._preview_cache = r.get('data', {})
        return self._preview_cache

    # ── 语义种子解析 (target_code → target_id) ──
    def _build_code_maps(self) -> Dict[str, Dict[str, int]]:
        """从 preview 数据建立 code → id 映射 (BO / 关系 / SM 三个字典)."""
        d = self.preview()
        bo_map: Dict[str, int] = {}
        for b in d.get('business_objects', []):
            if b.get('code'):
                bo_map[b['code']] = b['id']
        sm_map: Dict[str, int] = {}
        for m in d.get('service_modules', []):
            if m.get('code'):
                sm_map[m['code']] = m['id']
        rel_map: Dict[str, int] = {}
        for r in d.get('relationships', []):
            if r.get('code'):
                rel_map[r['code']] = r['id']
        return {'business_object': bo_map, 'service_module': sm_map, 'relationship': rel_map}

    def resolve_targets(self, seeds: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """语义种子 → 物理种子: 把 target_code 解析成 target_id (幂等查重仍按 id).
        兼容旧 manifest: seed 已带 target_id 时直接使用, 不解析.
        解析失败 → 抛 ValueError, 附可用 code 示例 (帮助排查 manifest 笔误)."""
        maps = self._build_code_maps()
        resolved: List[Dict[str, Any]] = []
        for s in seeds:
            tt = s['target_type']
            out = dict(s)
            if s.get('target_id') is not None:
                resolved.append(out)
                continue
            code = s.get('target_code')
            if not code:
                raise ValueError(f'seed 缺少 target_id/target_code: {s}')
            tid = maps.get(tt, {}).get(code)
            if tid is None:
                samples = sorted(maps.get(tt, {}).keys())[:8]
                raise ValueError(
                    f'无法解析 target_code={code!r} (target_type={tt}). '
                    f'可用 code 示例: {samples}. 可先跑 --probe 探测当前环境. '
                    f'(语义种子要求 code 在当前版本/产品中存在)')
            out['target_id'] = tid
            resolved.append(out)
        return resolved

    def probe(self) -> Dict[str, Any]:
        """探测候选目标: 输出 scope 内 BO / 关系 / 子域 SM (供自定义 seed manifest)."""
        d = self.preview()
        scope_bo = {b['id'] for b in d.get('business_objects', [])
                    if b.get('id') in _SCOPE_BO_DEFAULT}
        rels_in_scope = [r for r in d.get('relationships', [])
                         if r.get('source_bo_id') in _SCOPE_BO_DEFAULT
                         and r.get('target_bo_id') in _SCOPE_BO_DEFAULT]
        sms_sub299 = [m for m in d.get('service_modules', [])
                      if m.get('sub_domain_id') == 299]
        return {
            'version_id': VERSION_ID,
            'product_code': PRODUCT_CODE,
            'bo_in_scope': sorted(scope_bo),
            'rels_in_scope': [{'id': r['id'], 'code': r.get('code'),
                               'source_bo_id': r.get('source_bo_id'),
                               'target_bo_id': r.get('target_bo_id')}
                              for r in rels_in_scope[:8]],
            'sm_sub299': [{'id': m['id'], 'code': m.get('code'), 'name': m.get('name')}
                          for m in sms_sub299],
        }

    # ── 备注 CRUD ──
    def get_by_target(self, target_type: str, target_id: int) -> List[Dict[str, Any]]:
        r = self._req(f'/api/v1/annotations/by-target?target_type={target_type}'
                      f'&target_id={target_id}')
        return r.get('data', []) if r.get('success') else []

    def create(self, target_type: str, target_id: int,
               category: str, content: str) -> bool:
        r = self._req('/api/v1/annotations', method='POST', data={
            'target_type': target_type, 'target_id': target_id,
            'category': category, 'content': content,
        })
        ok = r.get('success') is True
        if not ok:
            print(f'    [FAIL] create {target_type}:{target_id} [{category}] → {r.get("error") or r.get("message")}')
        return ok

    def delete(self, annotation_id: int) -> bool:
        r = self._req(f'/api/v1/annotations/{annotation_id}', method='DELETE')
        return r.get('success') is True

    # ── 种子生命周期 ──
    def inject(self, seeds: List[Dict[str, Any]]) -> Dict[str, Any]:
        """幂等注入: [语义种子 2026-08-02] 先 code→id 解析, 再按
        (target_type, target_id, content) 查重, 已存在则跳过."""
        print(f'\n[chart_seed] 注入 {len(seeds)} 条种子 (幂等)')
        try:
            resolved = self.resolve_targets(seeds)
        except ValueError as e:
            print(f'[chart_seed] 种子解析失败: {e}')
            return {'created': 0, 'skipped': 0, 'failed': len(seeds), 'resolve_error': str(e)}
        stats = {'created': 0, 'skipped': 0, 'failed': 0}
        for s in resolved:
            tt, tid = s['target_type'], s['target_id']
            existing = {a.get('content') for a in self.get_by_target(tt, tid)}
            if s['content'] in existing:
                print(f'  [SKIP] {tt}:{tid} [{s["category"]}] 已存在')
                stats['skipped'] += 1
                continue
            if self.create(tt, tid, s['category'], s['content']):
                print(f'  [OK]   {tt}:{tid} [{s["category"]}] {s["content"][:40]}')
                stats['created'] += 1
                time.sleep(0.2)  # 避免连发过快
            else:
                stats['failed'] += 1
        print(f'[chart_seed] 注入完成: created={stats["created"]} skipped={stats["skipped"]} failed={stats["failed"]}')
        return stats

    def list_seeded(self) -> List[Dict[str, Any]]:
        """列出所有 [E2E-SEED] 前缀备注 (按默认种子目标聚合)."""
        out: List[Dict[str, Any]] = []
        try:
            targets = {(s['target_type'], s['target_id'])
                       for s in self.resolve_targets(DEFAULT_SEEDS)}
        except ValueError as e:
            print(f'[chart_seed] 种子解析失败, 无法聚合: {e}')
            return out
        for tt, tid in sorted(targets):
            for a in self.get_by_target(tt, tid):
                if (a.get('content') or '').startswith(SEED_PREFIX):
                    out.append({
                        'id': a.get('id'), 'target_type': tt, 'target_id': tid,
                        'category': a.get('category'),
                        'content': (a.get('content') or '')[:60],
                        'created_at': a.get('created_at'),
                    })
        return out

    def cleanup(self) -> Dict[str, Any]:
        """清理种子: 删除所有 [E2E-SEED] 前缀备注 (安全边界, 不碰真实数据)."""
        print('\n[chart_seed] 清理种子 (按 [E2E-SEED] 前缀)')
        stats = {'deleted': 0, 'failed': 0}
        items = self.list_seeded()
        for it in items:
            if self.delete(it['id']):
                print(f'  [OK]   删除 annotation#{it["id"]} {it["target_type"]}:{it["target_id"]} [{it["category"]}]')
                stats['deleted'] += 1
            else:
                print(f'  [FAIL] 删除 annotation#{it["id"]} 失败')
                stats['failed'] += 1
        print(f'[chart_seed] 清理完成: deleted={stats["deleted"]} failed={stats["failed"]}')
        return stats


# scope 内 BO 集合 (SCOPE_BO_DEFAULT, 与 chart_fixtures.py 一致)
_SCOPE_BO_DEFAULT = {3220, 3218, 3221, 2797, 2788, 2793, 1839, 2896, 3219, 2784,
                     2792, 2781, 2779, 1838, 2780, 2795, 2794, 1637, 2789, 2777,
                     2778, 2782, 2785, 1636, 2796, 2783, 2790, 2791, 2786, 2787}


def _load_seed_manifest(path: Optional[str]) -> List[Dict[str, Any]]:
    if not path:
        return DEFAULT_SEEDS
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'seed manifest 不存在: {p}')
    data = json.loads(p.read_text(encoding='utf-8'))
    seeds = data.get('seeds', data) if isinstance(data, dict) else data
    for s in seeds:
        s['content'] = f'{SEED_PREFIX} {s["content"].lstrip()}'.strip() \
            if not str(s.get('content', '')).startswith(SEED_PREFIX) \
            else s['content']
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser(description='图表 E2E 通用种子数据工具')
    parser.add_argument('--probe', action='store_true', help='探测候选目标 (BO/关系/SM)')
    parser.add_argument('--inject', action='store_true', help='幂等注入种子备注')
    parser.add_argument('--seed-manifest', default=None, help='自定义 seed manifest JSON')
    parser.add_argument('--status', action='store_true', help='列出已注入种子')
    parser.add_argument('--cleanup', action='store_true', help='按 [E2E-SEED] 前缀清理')
    args = parser.parse_args()

    try:
        client = SeedClient()
    except RuntimeError as e:
        print(f'[chart_seed] 初始化失败: {e}')
        sys.exit(1)

    if args.probe:
        p = client.probe()
        print(f'\n[probe] 版本 {p["version_id"]} / 产品 {p["product_code"]}')
        print(f'  scope 内 BO ({len(p["bo_in_scope"])}): {p["bo_in_scope"][:12]} ...')
        print(f'  scope 内关系 (前 8):')
        for r in p['rels_in_scope']:
            print(f'    id={r["id"]} {r["code"]} (src={r["source_bo_id"]} → tgt={r["target_bo_id"]})')
        print(f'  子域 299 的 SM:')
        for m in p['sm_sub299']:
            print(f'    id={m["id"]} {m["code"]} {m["name"]}')

    if args.inject:
        seeds = _load_seed_manifest(args.seed_manifest)
        client.inject(seeds)

    if args.status:
        items = client.list_seeded()
        print(f'\n[status] 已注入种子: {len(items)} 条')
        for it in items:
            print(f'  #{it["id"]} {it["target_type"]}:{it["target_id"]} [{it["category"]}] {it["content"]}')

    if args.cleanup:
        client.cleanup()

    if not (args.probe or args.inject or args.status or args.cleanup):
        parser.print_help()


if __name__ == '__main__':
    main()
