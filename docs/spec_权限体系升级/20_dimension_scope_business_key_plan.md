# Spec 20 实施计划: 维度范围业务键锚定 (Dimension Scope Business Key)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `dimension_values` 支持业务键字符串锚点（如 `["SCM"]`），运行时以动态子查询解析（新版本/新域自动生效，无需 re-derive），解析失败 fail-closed（`1=0`），存量数字 ID 行为完全不变。

**Architecture:** 策略 A —— `expand_dimension_values` 签名与返回不变（锚点解析为当刻 ID 快照进 `expanded`，所有外部调用方零改动）；新增 `expand_dimension_values_detail` 额外返回 `(native_values, anchor_map, inherited_from_anchor, failed_anchors)`；仅 `derive_data_conditions` 使用 detail 版本把锚点生成为 **RAW SQL 子查询**（`code IN ('SCM')`），经 `derivation_pipeline` 现有 RAW 通道（`include=[{field:'*',op:'RAW',value:sql}]` → `condition_parser` RAW op 纯透传）物化与消费。SQL 无 params 通道（`return value, []`），锚点字符串内联转义 + 保存端白名单双保险。

**Tech Stack:** Python / Flask / SQLite（元数据驱动 BOFramework），pytest（`TEST_ENTRY=1`），无新依赖。

**Spec:** `docs/spec_权限体系升级/20_dimension_scope_business_key.md`

> **执行状态 (2026-09-11 完成)**: Task 1-8 + Task 10 全部完成; Task 9 完成 P3 框架（矩阵锚点展示 + resolve-preview 水合 + 保存警示, commit 2829183），Rule Builder 内「跨版本/仅此实例」选择器为后续跟进项。提交链: fabb26a → 52a0679 → 210ec90 → 808d0da → 50d64ae → 7402fe1 → c04ebac → 2829183。验收证据见 Spec §11。

---

## 代码核查结论（2026-09-06，全部实测）

| # | 事实 | 位置 |
|---|------|------|
| 1 | 注入点：非数字被 `isdigit()` 过滤后静默丢弃（fail-open） | `dimension_scope_engine.py:354-356` |
| 2 | 爆破点：chain 链尾 `str(int(v))` 遇字符串抛 ValueError | `dimension_scope_engine.py:763` |
| 3 | exclude 解析对字符串安全跳过 | `dimension_scope_engine.py:1056` |
| 4 | RAW op 纯透传 `return value, []`（无 params 通道） | `condition_parser.py:131-138` |
| 5 | 非 wildcard intent 存 RAW SQL 字符串快照 | `derivation_pipeline.py:537-541` |
| 6 | `CODE_FIELD_MAP` 已存在（dim→'code'） | `permission_dimension_engine.py:91-97` |
| 7 | 保存归一对纯字符串放行原样落库；v083 迁移只处理 dict 不碰字符串 | `permission_set_dimension_scope_api.py:42-70` |
| 8 | RAW SQL 测试守卫只扫 test 文件 + 只匹配 INSERT/UPDATE/DELETE，SELECT 子查询不受限 | `tests/conftest.py:1132-1190` |
| 9 | `expand_dimension_values` 外部调用方（manage_api/special_routes_api/write_scope_interceptor×6）全部消费 ID 集合 | 全仓 grep |
| 10 | 引擎未 import os（开关需补）；测试守卫风格 `TEST_ENTRY='1'` | `dimension_scope_engine.py:15-24` |

---

## Task 1: 引擎基础 — 开关与锚点解析方法

**Files:**
- Modify: `meta/services/dimension_scope_engine.py:15-24`（import）、`:212` 后（新方法）
- Test: `meta/tests/test_dim_scope_bizkey.py`（新建）

- [ ] **Step 1.1: 写失败测试**

新建 `meta/tests/test_dim_scope_bizkey.py`：

```python
# -*- coding: utf-8 -*-
"""
[FILE] test_dim_scope_bizkey.py
[DESCRIPTION] Spec 20 维度范围业务键锚定 单元测试

[覆盖场景]
  1. _resolve_bizkeys 跨版本解析 (同 code 多 ID)
  2. 锚点 0 命中检测
  3. 开关 DIM_SCOPE_BIZKEY_ENABLED
  4. expand_detail: native/anchors/failed 分离
  5. chain 链尾锚点子查询 + 单引号转义
  6. derive_data_conditions 动态 SQL (G2 铁证见集成测试类)
  7. fail-closed: 锚点失败 → 1=0
  8. 回归: 纯数字/wildcard/all/exclude 行为不变
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ['TEST_ENTRY'] = '1'  # 绕过 conftest 硬阻断

import sqlite3
import pytest

from meta.services.dimension_scope_engine import DimensionScopeEngine


SCHEMA = """
CREATE TABLE products (id INTEGER PRIMARY KEY, code TEXT, name TEXT);
CREATE TABLE versions (id INTEGER PRIMARY KEY, code TEXT, name TEXT, product_id INTEGER);
CREATE TABLE domains (id INTEGER PRIMARY KEY, code TEXT, domain_name TEXT, version_id INTEGER);
CREATE TABLE sub_domains (id INTEGER PRIMARY KEY, code TEXT, sub_domain_name TEXT, domain_id INTEGER);
CREATE TABLE service_modules (id INTEGER PRIMARY KEY, code TEXT, name TEXT, sub_domain_id INTEGER);
CREATE TABLE business_objects (id INTEGER PRIMARY KEY, code TEXT, name TEXT, service_module_id INTEGER);
CREATE TABLE permission_set_dimension_scopes (
    id INTEGER PRIMARY KEY,
    permission_set_id INTEGER,
    dimension_code TEXT,
    dimension_values TEXT,
    inherit_children INTEGER DEFAULT 1,
    scope_mode TEXT DEFAULT 'include'
);
"""

class SqliteDS:
    """最小数据源适配: 引擎只调用 ds.execute(sql, params).fetchall()"""
    def __init__(self, conn):
        self._conn = conn
    def execute(self, sql, params=None):
        cur = self._conn.execute(sql, params or [])
        cur.fetchall = lambda: list(cur.fetchall())
        return cur


@pytest.fixture
def db():
    conn = sqlite3.connect(':memory:')
    conn.executescript(SCHEMA)
    # 两个版本下同 code='SCM' 的领域 (业务键跨版本稳定的 DB 事实)
    conn.execute("INSERT INTO products VALUES (1,'P_A','产品A')")
    conn.execute("INSERT INTO products VALUES (2,'P_B','产品B')")
    conn.execute("INSERT INTO versions VALUES (10,'v01','v1',1)")
    conn.execute("INSERT INTO versions VALUES (11,'v02','v2',1)")
    conn.execute("INSERT INTO versions VALUES (20,'v01','v1',2)")
    conn.execute("INSERT INTO domains VALUES (64,'SCM','供应链云',10)")
    conn.execute("INSERT INTO domains VALUES (88,'SCM','供应链云',11)")
    conn.execute("INSERT INTO domains VALUES (70,'FIN','财务云',10)")
    conn.execute("INSERT INTO domains VALUES (90,'SCM','供应链云',20)")
    conn.execute("INSERT INTO sub_domains VALUES (301,'SCM_PL','计划',64)")
    conn.execute("INSERT INTO sub_domains VALUES (302,'SCM_PUR','采购',64)")
    conn.commit()
    yield SqliteDS(conn)
    conn.close()


def _add_scope(db, ps_id, dim, vals, mode='include', inherit=1):
    db._conn.execute(
        "INSERT INTO permission_set_dimension_scopes "
        "(permission_set_id, dimension_code, dimension_values, inherit_children, scope_mode) "
        "VALUES (?,?,?,?,?)",
        (ps_id, dim, __import__('json').dumps(vals), inherit, mode))
    db._conn.commit()


class TestResolveBizkeys:
    def test_cross_version_resolution(self, db):
        eng = DimensionScopeEngine(db)
        result = eng._resolve_bizkeys('domain', ['SCM'])
        assert set(result['SCM']) == {64, 88, 90}  # 跨 3 版本全部命中

    def test_unresolved_code(self, db):
        eng = DimensionScopeEngine(db)
        result = eng._resolve_bizkeys('domain', ['NOPE'])
        assert result['NOPE'] == set()

    def test_unknown_dim_returns_empty(self, db):
        eng = DimensionScopeEngine(db)
        assert eng._resolve_bizkeys('nonexistent', ['SCM']) == {}
```

- [ ] **Step 1.2: 跑测试确认失败**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py -v -x`
Expected: FAIL — `AttributeError: 'DimensionScopeEngine' object has no attribute '_resolve_bizkeys'`

- [ ] **Step 1.3: 最小实现**

`meta/services/dimension_scope_engine.py` 三处修改：

(a) import 块（第 15-24 行）改为：

```python
import json
import logging
import os
from typing import Dict, List, Set, Optional, Tuple

from meta.Core.models import registry  # ← 原样保留, 此行勿动, 仅示意上下文
from meta.core.dimension_object_mapping_loader import (
    get_dimension_object_mapping_loader,
)
from meta.services.permission_dimension_engine import RESOURCE_TABLE_MAP, \
    PARENT_FIELD_MAP, CODE_FIELD_MAP

logger = logging.getLogger(__name__)
```

注意：`from meta.Core.models import registry` 是原文件第 19 行原文，只**新增** `import os`、typing 加 `Tuple`、`CODE_FIELD_MAP`。

(b) `class DimensionScopeEngine:` 内（`__init__` 之后）新增：

```python
    # [Spec 20] 业务键锚点开关: '0' 关闭; 关闭时锚点一律 fail-closed (1=0), 绝不回退 fail-open
    BIZKEY_ENV_FLAG = 'DIM_SCOPE_BIZKEY_ENABLED'

    @staticmethod
    def _bizkey_enabled() -> bool:
        return os.environ.get(DimensionScopeEngine.BIZKEY_ENV_FLAG, '1') != '0'

    def _resolve_bizkeys(self, dim_code: str, codes: List[str]) -> Dict[str, Set[int]]:
        """[Spec 20] 业务键锚点解析: code → 命中 ID 集合 (跨所有版本)

        业务键 = 维度表的 code 列 (CODE_FIELD_MAP), 唯一约束 (version_id, code),
        同 code 跨版本复用 → 解析自然命中全部版本的同名实体。

        Returns:
            {code: set(命中ID)}; 未命中的 code → 空集合; 未知维度 → {}
        """
        table = RESOURCE_TABLE_MAP.get(dim_code)
        code_field = CODE_FIELD_MAP.get(dim_code)
        if not table or not code_field or not codes:
            return {}
        try:
            ph = ','.join('?' * len(codes))
            rows = self._ds.execute(
                f"SELECT id, {code_field} FROM {table} WHERE {code_field} IN ({ph})",
                [str(c) for c in codes],
            ).fetchall()
        except Exception as e:
            logger.warning(f'[_resolve_bizkeys] query failed dim={dim_code}: {e}')
            return {c: set() for c in codes}
        result: Dict[str, Set[int]] = {c: set() for c in codes}
        for row_id, row_code in rows:
            if row_code in result and row_id is not None:
                result[row_code].add(row_id)
        return result
```

- [ ] **Step 1.4: 跑测试确认通过**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py -v`
Expected: 3 PASS

- [ ] **Step 1.5: Commit**

```bash
git add meta/services/dimension_scope_engine.py meta/tests/test_dim_scope_bizkey.py
git commit -m "feat(spec20): dimension scope engine bizkey switch + _resolve_bizkeys"
```

---

## Task 2: expand_dimension_values_detail — native/anchors/失败标记分离

**Files:**
- Modify: `meta/services/dimension_scope_engine.py:216-388`（`expand_dimension_values` 重构为 detail 薄包装）
- Test: `meta/tests/test_dim_scope_bizkey.py`（追加）

- [ ] **Step 2.1: 写失败测试**（追加到测试文件）

```python
class TestExpandDetail:
    def test_native_and_anchors_separated(self, db):
        _add_scope(db, 1, 'domain', [70, 'SCM'])
        eng = DimensionScopeEngine(db)
        expanded, native, anchors, inherited, failed = eng.expand_dimension_values_detail(1)
        assert native['domain'] == {70}
        assert anchors['domain'] == {'SCM'}
        # expanded 含锚点解析快照 (旧消费方兼容) + 数字
        assert expanded['domain'] == {70, 64, 88, 90}
        assert failed.get('domain') is None

    def test_unresolved_anchor_marked_failed(self, db):
        _add_scope(db, 1, 'domain', ['SCM', 'TYPO_X'])
        eng = DimensionScopeEngine(db)
        expanded, native, anchors, inherited, failed = eng.expand_dimension_values_detail(1)
        assert failed['domain'] == {'TYPO_X'}   # 混合: 部分失败 → 整体标失败 (严格模式)

    def test_flag_off_fails_closed(self, db, monkeypatch):
        monkeypatch.setenv('DIM_SCOPE_BIZKEY_ENABLED', '0')
        _add_scope(db, 1, 'domain', ['SCM'])
        eng = DimensionScopeEngine(db)
        expanded, native, anchors, inherited, failed = eng.expand_dimension_values_detail(1)
        assert failed['domain'] == {'SCM'}
        assert not anchors.get('domain')

    def test_legacy_expand_unchanged_signature(self, db):
        _add_scope(db, 1, 'domain', [70])
        eng = DimensionScopeEngine(db)
        assert eng.expand_dimension_values(1) == {'domain': {70}}

    def test_anchor_inherit_children_snapshot(self, db):
        _add_scope(db, 1, 'domain', ['SCM'], inherit=1)
        eng = DimensionScopeEngine(db)
        expanded, native, anchors, inherited, failed = eng.expand_dimension_values_detail(1)
        # 锚点继承产物进 expanded (旧消费方) 且记入 inherited_from_anchor (SQL 侧动态化用)
        assert expanded['sub_domain'] == {301, 302}
        assert inherited['sub_domain']['domain'] == {301, 302}

    def test_numeric_inherit_not_marked_inherited(self, db):
        _add_scope(db, 1, 'domain', [64], inherit=1)
        eng = DimensionScopeEngine(db)
        expanded, native, anchors, inherited, failed = eng.expand_dimension_values_detail(1)
        assert expanded['sub_domain'] == {301, 302}
        assert 'sub_domain' not in inherited   # 数字继承是快照语义 (G4 不变)
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py::TestExpandDetail -v`
Expected: FAIL — no attribute `expand_dimension_values_detail`

- [ ] **Step 2.3: 重构 expand**

`expand_dimension_values`（216-388 行）整体重命名 + 重构。核心：**普通数值分支**（原 353-360 行）替换为锚点感知版；3 个向下展开块（`all` 分支 243-279、wildcard 分支 321-350、普通分支 362-387）抽成一个私有方法消除三份重复：

```python
    def expand_dimension_values(self, role_id: int) -> Dict[str, Set[int]]:
        """[Spec 20] 兼容签名: 锚点解析为当刻 ID 快照进 expanded, 旧调用方行为不变"""
        expanded, _, _, _, _ = self.expand_dimension_values_detail(role_id)
        return expanded

    def expand_dimension_values_detail(
        self, role_id: int
    ) -> Tuple[Dict[str, Set[int]], Dict[str, Set[int]],
               Dict[str, Set[str]], Dict[str, Dict[str, Set[int]]],
               Dict[str, Set[str]]]:
        """[Spec 20] 扩展版维度展开

        Returns:
            expanded:  {dim: set(ids)}  — 与旧版语义一致 (含锚点快照, 供
                        derive_recommended_menus / write_scope_interceptor 等旧消费方)
            native:    {dim: set(ids)}  — scope 中直接写的数字 ID (生成 SQL 的原生部分)
            anchors:   {dim: set(code)} — 业务键锚点 (生成 SQL 的动态部分)
            inherited: {child_dim: {anchor_dim: set(ids)}} — 锚点 scope 向下继承的
                        快照 (derive_data_conditions 需将其从 native 剔除并动态化)
            failed:    {dim: set(code)} — 解析 0 命中 / 开关关闭的锚点 (fail-closed 依据)
        """
        scopes = self._load_scopes(role_id)
        expanded: Dict[str, Set[int]] = {}
        native: Dict[str, Set[int]] = {}
        anchors: Dict[str, Set[str]] = {}
        inherited: Dict[str, Dict[str, Set[int]]] = {}
        failed: Dict[str, Set[str]] = {}
        bizkey_on = self._bizkey_enabled()

        def _record(dim, ids, from_anchor_dim=None):
            if not ids:
                return
            expanded.setdefault(dim, set()).update(ids)
            if from_anchor_dim:
                inherited.setdefault(dim, {}).setdefault(from_anchor_dim, set()).update(ids)

        def _expand_down_chain(start_dim, start_ids, from_anchor_dim=None):
            """沿 HIERARCHY_CHAIN 向下展开 (笛卡尔保留: 子维度显式 include 时 break)"""
            try:
                idx = HIERARCHY_CHAIN.index(start_dim)
            except ValueError:
                return
            current_ids = set(start_ids)
            for next_dim in HIERARCHY_CHAIN[idx + 1:]:
                if self._has_explicit_include_for_dim(scopes, next_dim):
                    logger.info(
                        f'[P1-CARTESION] parent={start_dim}, child={next_dim} '
                        f'explicit include — break inherit chain')
                    break
                parent_field = PARENT_FIELD_MAP.get(next_dim)
                child_table = RESOURCE_TABLE_MAP.get(next_dim)
                if not parent_field or not child_table or not current_ids:
                    break
                ph = ','.join('?' * len(current_ids))
                rows = self._ds.execute(
                    f"SELECT id FROM {child_table} WHERE {parent_field} IN ({ph})",
                    list(current_ids)).fetchall()
                current_ids = {row[0] for row in rows}
                if not current_ids:
                    break
                _record(next_dim, current_ids, from_anchor_dim=from_anchor_dim)

        for scope in scopes:
            code = scope['dimension_code']
            scope_mode = scope.get('scope_mode', 'include')
            if scope_mode == 'exclude':
                continue  # [P5] exclude 由 _load_exclude_values 处理
            if scope_mode == 'all':
                all_ids = self._get_all_dimension_ids(code)
                if not all_ids:
                    continue
                _record(code, all_ids)
                logger.info(f'[P1-WILDCARD] scope_mode=all: role_id={role_id}, '
                            f'dimension={code}, all_ids_count={len(all_ids)}')
                if scope.get('inherit_children', 1) == 1:
                    _expand_down_chain(code, all_ids)
                continue

            raw_dv = scope.get('dimension_values')
            if raw_dv is None:
                raw_dv = scope.get('inherit_children')
                if raw_dv is None:
                    continue
            if isinstance(raw_dv, str):
                try:
                    parsed = json.loads(raw_dv)
                except (json.JSONDecodeError, TypeError):
                    continue
            elif isinstance(raw_dv, (list, tuple)):
                parsed = list(raw_dv)
            else:
                continue

            if any(str(v).strip() == '*' for v in parsed):
                all_ids = self._get_all_dimension_ids(code)
                if not all_ids:
                    continue
                _record(code, all_ids)
                logger.info(f'[P5-WILDCARD] dimension_values=["*"]: role_id={role_id}, '
                            f'dimension={code}, all_ids_count={len(all_ids)}')
                if scope.get('inherit_children', 1) == 1:
                    _expand_down_chain(code, all_ids)
                continue

            # ── [Spec 20] 普通分支: 数字 + 业务键锚点分离 ──
            numeric_vals = set(int(x) for x in parsed
                               if str(x).lstrip('-').isdigit())
            anchor_codes = [str(x).strip() for x in parsed
                            if isinstance(x, str) and str(x).strip() != '*'
                            and not str(x).lstrip('-').isdigit()]

            if numeric_vals:
                native.setdefault(code, set()).update(numeric_vals)
                _record(code, numeric_vals)

            if anchor_codes:
                if bizkey_on:
                    resolved = self._resolve_bizkeys(code, anchor_codes)
                    miss = {c for c in anchor_codes if not resolved.get(c)}
                    if miss:
                        # 严格模式 (Spec 20 §4.2): 任一锚点失败 → 整维度 fail-closed
                        failed.setdefault(code, set()).update(miss)
                        logger.warning(
                            f'[Spec20-BIZKEY] unresolved anchors: role_id={role_id}, '
                            f'dim={code}, codes={sorted(miss)} — dimension will be 1=0')
                        continue
                    snap_ids = set().union(*[resolved[c] for c in anchor_codes])
                    anchors.setdefault(code, set()).update(anchor_codes)
                    _record(code, snap_ids)
                    if scope.get('inherit_children') or scope.get('inherit_children') == 1:
                        _expand_down_chain(code, snap_ids, from_anchor_dim=code)
                else:
                    # 开关 OFF → fail-closed (绝不回退 fail-open)
                    failed.setdefault(code, set()).update(anchor_codes)
                    logger.warning(
                        f'[Spec20-BIZKEY] flag off: role_id={role_id}, dim={code}, '
                        f'codes={sorted(anchor_codes)} — dimension will be 1=0')
                continue

            if not numeric_vals:
                continue

            if not (scope.get('inherit_children') or scope.get('inherit_children') == 1):
                continue
            _expand_down_chain(code, numeric_vals)
        return expanded, native, anchors, inherited, failed
```

关键语义（与旧版 diff）：
- 数字路径行为完全不变（`_expand_down_chain` 是原 362-387 行的原样抽取）。
- 锚点失败 `continue` 前已记入 `failed` —— 注意不进 `expanded`（该维度无值）。
- 锚点继承产物同时进 `expanded`（旧消费方）与 `inherited`（SQL 动态化用）。

- [ ] **Step 2.4: 全量跑本文件测试 + 引擎现有回归**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py meta/tests/test_dim_scope_conflict.py -v`
Expected: 全 PASS

- [ ] **Step 2.5: Commit**

```bash
git add meta/services/dimension_scope_engine.py meta/tests/test_dim_scope_bizkey.py
git commit -m "feat(spec20): expand_dimension_values_detail with native/anchors/failed separation"
```

---

## Task 3: chain 链尾锚点子查询 + 转义

**Files:**
- Modify: `meta/services/dimension_scope_engine.py:619-784`（`_build_chain_condition` 签名与链尾）
- Test: `meta/tests/test_dim_scope_bizkey.py`（追加）

- [ ] **Step 3.1: 写失败测试**

```python
class TestChainAnchor:
    def _ps_with_anchor(self, db):
        _add_scope(db, 1, 'domain', ['SCM'], inherit=0)

    def test_chain_tail_embeds_code_subquery(self, db):
        self._ps_with_anchor(db)
        eng = DimensionScopeEngine(db)
        # business_object 沿链追溯到 domain (leaf=service_module_id)
        cond = eng._build_chain_condition(
            'business_object', 'domain', [], anchor_codes=['SCM'])
        assert cond is not None
        assert "code IN ('SCM')" in cond
        assert 'domains' in cond and 'versions' in cond and 'sub_domains' in cond
        # 不含任何数字快照
        assert ' 64' not in cond and ' 88' not in cond

    def test_chain_mixed_native_and_anchor(self, db):
        eng = DimensionScopeEngine(db)
        cond = eng._build_chain_condition(
            'business_object', 'domain', [70], anchor_codes=['SCM'])
        assert 'id IN (70)' in cond
        assert "code IN ('SCM')" in cond

    def test_quote_escaping(self, db):
        eng = DimensionScopeEngine(db)
        cond = eng._build_chain_condition(
            'business_object', 'domain', [], anchor_codes=["SCM'--"])
        assert "''" in cond          # 单引号已翻倍转义
        assert "SCM'--" not in cond  # 原始未转义串不出现

    def test_no_inputs_returns_none(self, db):
        eng = DimensionScopeEngine(db)
        assert eng._build_chain_condition('business_object', 'domain', []) is None
```

- [ ] **Step 3.2: 跑测试确认失败**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py::TestChainAnchor -v`
Expected: FAIL — unexpected keyword argument `anchor_codes`

- [ ] **Step 3.3: 改链尾**

`_build_chain_condition` 两处修改：

(a) 签名（620-625 行）追加参数：

```python
    def _build_chain_condition(
        self,
        resource_type: str,
        target_dim: str,
        dim_vals: List[int],
        custom_field: Optional[str] = None,
        anchor_codes: Optional[List[str]] = None,
    ) -> Optional[str]:
```

(b) SQL 构造段（原 762-768 行）替换：

```python
        # ─────────────── 2. 构造 SQL ───────────────
        # [Spec 20] 链尾支持业务键锚点: WHERE (id IN (n1,n2)) OR (code IN ('a1','a2'))
        # RAW 通道无 params (condition_parser RAW → return value, []) → 内联转义单引号
        val_parts = []
        if dim_vals:
            vals = ', '.join(str(int(v)) for v in dim_vals)
            val_parts.append(f"id IN ({vals})")
        if anchor_codes:
            code_field = CODE_FIELD_MAP.get(target_dim, 'code')
            quoted = ', '.join("'" + str(c).replace("'", "''") + "'"
                               for c in anchor_codes)
            val_parts.append(f"{code_field} IN ({quoted})")
        if not val_parts:
            return None

        # cur_query 初始 = target_dim 表的 id 列表
        # chain[-1] = (target_dim_table, None, None)
        target_dim_table = chain[-1][0]
        cur_query = (f"SELECT DISTINCT id FROM {target_dim_table} "
                     f"WHERE {' OR '.join(val_parts)}")
```

外层包裹循环（770-784 行）不动。

- [ ] **Step 3.4: 跑测试确认通过 + 回归**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py meta/tests/test_dim_scope_conflict.py -v`
Expected: 全 PASS

- [ ] **Step 3.5: Commit**

```bash
git add meta/services/dimension_scope_engine.py meta/tests/test_dim_scope_bizkey.py
git commit -m "feat(spec20): chain tail supports bizkey anchor subquery with escaping"
```

---

## Task 4: derive_data_conditions 锚点感知（核心）

**Files:**
- Modify: `meta/services/dimension_scope_engine.py:391-617`
- Test: `meta/tests/test_dim_scope_bizkey.py`（追加）

设计要点（核查结论 #1/#2/#4 落点）：
- 开头改用 `expand_dimension_values_detail`。
- `native_for_sql[dim] = expanded[dim] - inherited[dim]所有锚点源ID并集`。
- 新私有方法 `_anchor_dynamic_condition` 统一生成锚点动态条件（fk 型单层 / chain 型嵌套）。
- fail-closed 落点：`failed_anchors[dim]` 非空 → 该 dim 的 parts 直接 `1 = 0`。
- fk_expanded 遇锚点 dim → 转 `_build_chain_condition(resource, dim, native, anchor_codes=...)`。

- [ ] **Step 4.1: 写失败测试**

```python
class TestDeriveConditions:
    def test_pure_anchor_domain_self_direct(self, db):
        _add_scope(db, 1, 'domain', ['SCM'], inherit=0)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        c = conds.get('domain', '')
        assert "code IN ('SCM')" in c and ' 64' not in c and ' 88' not in c

    def test_anchor_inherit_subdomain_dynamic(self, db):
        _add_scope(db, 1, 'domain', ['SCM'], inherit=1)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        c = conds.get('sub_domain', '')
        # 动态: 沿父 FK 子查询, 不含子快照 ID
        assert 'domain_id IN' in c and "code IN ('SCM')" in c
        assert '301' not in c and '302' not in c

    def test_anchor_fail_closed(self, db):
        _add_scope(db, 1, 'domain', ['TYPO_X'], inherit=0)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        assert conds.get('domain') == '1 = 0'

    def test_mixed_native_anchor_or(self, db):
        _add_scope(db, 1, 'domain', [70, 'SCM'], inherit=0)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        c = conds.get('domain', '')
        assert 'id IN (70)' in c and "code IN ('SCM')" in c

    def test_numeric_golden_regression(self, db):
        """G4: 纯数字 scope 生成 SQL 与旧逻辑完全一致"""
        _add_scope(db, 1, 'domain', [64], inherit=1)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        assert conds.get('domain') == 'id = 64'
        # 旧版: inherit 展开快照 → sub_domain.id IN (301,302)
        assert conds.get('sub_domain') == 'id IN (301,302)'

    def test_wildcard_regression(self, db):
        _add_scope(db, 1, 'domain', ['*'], inherit=1)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        assert '64' in conds.get('domain', '') and '88' in conds.get('domain', '')
```

- [ ] **Step 4.2: 跑测试确认失败**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py::TestDeriveConditions -v`
Expected: FAIL（数字 golden 中 sub_domain 断言可能因 sorting 通过，锚点用例全 FAIL）

- [ ] **Step 4.3: 实现**

(a) `derive_data_conditions` 第 414 行替换：

```python
        expanded, native_vals, anchor_map, inherited_map, failed_anchors = \
            self.expand_dimension_values_detail(role_id)
```

（`original_expanded` 417 行及向上展开 424-451 行不动——锚点快照在 expanded 里，向上展开行为与旧版一致。）

(b) 类内新增统一锚点条件方法：

```python
    def _anchor_dynamic_condition(
        self, resource_type: str, dim_code: str,
        native_ids: Set[int], anchor_codes: Set[str],
        binding_field: Optional[str] = None,
        filter_type: str = 'fk',
    ) -> Optional[str]:
        """[Spec 20] 锚点动态 SQL 条件 (fk 型单层子查询 / chain 型嵌套子查询)

        fk/direct:  {field} IN (SELECT id FROM {dim_table} WHERE (id IN (n)) OR (code IN ('a')))
        chain:      沿 HIERARCHY_CHAIN 嵌套, 链尾同上 (Task 3 已支持)
        resource==dim 且 field=id: 退化为 fk 型 (field=id)
        """
        if not anchor_codes:
            return None
        if filter_type == 'chain':
            return self._build_chain_condition(
                resource_type, dim_code, sorted(native_ids),
                custom_field=binding_field,
                anchor_codes=sorted(anchor_codes))
        # fk / direct 型: 单层子查询
        dim_table = RESOURCE_TABLE_MAP.get(dim_code)
        field = binding_field or 'id'
        if not dim_table:
            return None
        val_parts = []
        if native_ids:
            val_parts.append(
                f"id IN ({','.join(str(int(v)) for v in sorted(native_ids))})")
        code_field = CODE_FIELD_MAP.get(dim_code, 'code')
        quoted = ', '.join("'" + str(c).replace("'", "''") + "'"
                           for c in sorted(anchor_codes))
        val_parts.append(f"{code_field} IN ({quoted})")
        if not val_parts:
            return None
        return (f"{field} IN (SELECT id FROM {dim_table} "
                f"WHERE {' OR '.join(val_parts)})")
```

(c) yaml mapping 主循环（原 465-530 行）替换为：

```python
                for dim_code in expanded:
                    if not expanded[dim_code]:
                        continue
                    bindings = loader.get_bindings_for_bo(dim_code, resource_type)
                    if not bindings:
                        continue
                    # [Spec 20] native = expanded 剔除锚点继承快照 (快照由动态条件接管)
                    inherited_ids: Set[int] = set()
                    if dim_code in inherited_map:
                        for ids in inherited_map[dim_code].values():
                            inherited_ids |= ids
                    dim_native = expanded[dim_code] - inherited_ids
                    dim_anchors = anchor_map.get(dim_code, set())
                    if dim_native and not dim_anchors and dim_code not in failed_anchors \
                            and dim_code not in inherited_map:
                        vals = sorted(dim_native)
                    elif dim_native:
                        vals = sorted(dim_native)
                    else:
                        vals = []

                    binding_parts = []
                    # [Spec 20] fail-closed: 该维度锚点解析失败 → 1=0 (不生成其他条件)
                    if dim_code in failed_anchors:
                        binding_parts.append('1 = 0')
                    else:
                        for binding in bindings:
                            field = binding.get('field')
                            filter_type = binding.get('filter_type', 'direct')
                            if not field:
                                continue
                            if filter_type in ('direct', 'fk'):
                                if dim_anchors or dim_code in inherited_map:
                                    # 锚点/继承动态化 (fk 型)
                                    if dim_code == resource_type:
                                        # 自身维度: direct field=id → fk 型单层
                                        cond = self._anchor_dynamic_condition(
                                            resource_type, dim_code,
                                            dim_native, dim_anchors,
                                            binding_field=field)
                                    else:
                                        cond = self._anchor_dynamic_condition(
                                            resource_type, dim_code,
                                            dim_native, dim_anchors,
                                            binding_field=field)
                                    if cond:
                                        binding_parts.append(cond)
                                    elif vals:
                                        binding_parts.append(
                                            f"{field} IN ({','.join(str(v) for v in vals)})"
                                            if len(vals) > 1 else f"{field} = {vals[0]}")
                                elif vals:
                                    binding_parts.append(
                                        f"{field} IN ({','.join(str(v) for v in vals)})"
                                        if len(vals) > 1 else f"{field} = {vals[0]}")
                            elif filter_type == 'chain':
                                if dim_anchors:
                                    cond = self._build_chain_condition(
                                        resource_type, dim_code, vals,
                                        custom_field=field if field else None,
                                        anchor_codes=sorted(dim_anchors))
                                else:
                                    cond = self._build_chain_condition(
                                        resource_type, dim_code, vals,
                                        custom_field=field if field else None)
                                if cond:
                                    binding_parts.append(cond)
                            elif filter_type == 'fk_expanded':
                                if dim_anchors:
                                    # [Spec 20] 锚点 → 转 chain 动态 (快照 fk_expanded 不适用)
                                    cond = self._build_chain_condition(
                                        resource_type, dim_code, vals,
                                        anchor_codes=sorted(dim_anchors))
                                    if cond:
                                        binding_parts.append(cond)
                                    elif not vals:
                                        binding_parts.append('1 = 0')
                                else:
                                    child_ids = self._expand_down(
                                        dim_code, resource_type, vals)
                                    if child_ids:
                                        s = sorted(child_ids)
                                        binding_parts.append(
                                            f"{field} IN ({','.join(str(v) for v in s)})"
                                            if len(s) > 1 else f"{field} = {s[0]}")
                                    else:
                                        binding_parts.append('1 = 0')
                    if binding_parts:
                        if len(binding_parts) == 1:
                            parts.append(binding_parts[0])
                        else:
                            parts.append(f"({' OR '.join(binding_parts)})")
```

注意：`inherited_map` 中"子维度 direct 自身 binding"（resource=sub_domain, dim=sub_domain, field=id）时 `dim_anchors` 为空但 `dim_code in inherited_map` → 走 fk 型动态化，`binding_field='id'`，`dim_table='sub_domains'` → 生成 `id IN (SELECT id FROM sub_domains WHERE domain_id IN (SELECT ... domains ... code IN ('SCM')))`？——不对：fk 型单层的内层查的是 `dim_table`=sub_domains，条件只有 `id IN (native)`/`code IN`，而锚点在 domain 上。**修正**：resource==dim 且值来自上游锚点继承时，必须用 chain（resource → anchor_dim）。统一规则改为：

```python
                            if filter_type in ('direct', 'fk'):
                                src_anchor_dims = (sorted(inherited_map.get(dim_code, {}).keys())
                                                   if dim_code in inherited_map else [])
                                if dim_anchors or src_anchor_dims:
                                    if dim_anchors and not src_anchor_dims:
                                        cond = self._anchor_dynamic_condition(
                                            resource_type, dim_code,
                                            dim_native, dim_anchors,
                                            binding_field=field)
                                    else:
                                        # 值来自上游锚点继承 → 沿 chain 动态追溯到锚点源维度
                                        cond = self._build_chain_condition(
                                            resource_type,
                                            src_anchor_dims[0],
                                            sorted(dim_native),
                                            anchor_codes=sorted(
                                                anchor_map.get(src_anchor_dims[0], set())))
                                    if cond:
                                        binding_parts.append(cond)
                                    elif vals:  # chain 构造失败兜底: 用快照 (不放大)
                                        binding_parts.append(
                                            f"{field} IN ({','.join(str(v) for v in vals)})"
                                            if len(vals) > 1 else f"{field} = {vals[0]}")
                                elif vals:
                                    ... (原样数字分支)
```

（一个 dim 同时继承自多个锚点源维度时取第一个——当前 HIERARCHY_CHAIN 单父链下最多一个，防御性排序即可。）

(d) 老路径（531-561 行）不动（`use_yaml_mapping=False` 时 expanded 只有数字语义，锚点在此路径被忽略与旧版一致——加注释说明）。

- [ ] **Step 4.4: 跑测试确认通过**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py -v`
Expected: 全 PASS（含数字 golden）

- [ ] **Step 4.5: Commit**

```bash
git add meta/services/dimension_scope_engine.py meta/tests/test_dim_scope_bizkey.py
git commit -m "feat(spec20): derive_data_conditions generates dynamic anchor subqueries, fail-closed"
```

---

## Task 5: G2 集成铁证 — 新版本数据插入后 SQL 不变但命中

**Files:**
- Test: `meta/tests/test_dim_scope_bizkey.py`（追加）

- [ ] **Step 5.1: 写集成测试**

```python
class TestG2DynamicAcceptance:
    def test_new_version_domain_auto_covered(self, db):
        """G2 铁证: derive 的 SQL 不含新 ID, 但插入新版本 SCM 后执行命中

        模拟时序:
          t1: PS 配 domain 锚点 SCM → derive → 记录 SQL
          t2: 新建版本 v03 + domains(id=120, code='SCM')  ← 不 re-derive
          t3: 直接执行 t1 的 SQL → 命中 120  ← 动态性的证明
        """
        _add_scope(db, 1, 'domain', ['SCM'], inherit=1)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        sql_at_t1 = conds['domain']

        # t2: 新版本新域 (模拟版本升级, 不调用 derive)
        db._conn.execute(
            "INSERT INTO versions VALUES (12,'v03','v3',1)")
        db._conn.execute(
            "INSERT INTO domains VALUES (120,'SCM','供应链云',12)")
        db._conn.commit()

        # t3: SQL 字符串不变, 执行结果覆盖新域
        rows = db.execute(
            f"SELECT id FROM domains WHERE {sql_at_t1}").fetchall()
        ids = {r[0] for r in rows}
        assert {64, 88, 90, 120} <= ids
        assert 70 not in ids          # FIN 不误命中

    def test_subdomain_of_new_version_covered(self, db):
        _add_scope(db, 1, 'domain', ['SCM'], inherit=1)
        eng = DimensionScopeEngine(db)
        conds = eng.derive_data_conditions(1)
        sql_sub = conds['sub_domain']
        db._conn.execute("INSERT INTO domains VALUES (120,'SCM','供应链云',12)")
        db._conn.execute(
            "INSERT INTO sub_domains VALUES (401,'SCM_SALE','销售',120)")
        db._conn.commit()
        rows = db.execute(
            f"SELECT id FROM sub_domains WHERE {sql_sub}").fetchall()
        ids = {r[0] for r in rows}
        assert 401 in ids and 301 in ids
```

- [ ] **Step 5.2: 跑测试**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py::TestG2DynamicAcceptance -v`
Expected: 2 PASS（若 FAIL，说明某条路径仍有快照残留——按断言中的具体 ID 定位回 Task 4 对应分支）

- [ ] **Step 5.3: Commit**

```bash
git add meta/tests/test_dim_scope_bizkey.py
git commit -m "test(spec20): G2 dynamic acceptance - new version auto covered without re-derive"
```

---

## Task 6: 全链路回归

- [ ] **Step 6.1: 跑引擎相关全部测试**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py meta/tests/test_dim_scope_conflict.py meta/tests/test_intent_scope_adapter.py -v`
Expected: 全 PASS

- [ ] **Step 6.2: 跑 derivation_pipeline / write_scope 相关既有测试**（确认 RAW 通道无回归）

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests -k "derivation or pipeline or write_scope" -v 2>&1 | tail -20`
Expected: 无新增 FAIL（既有失败先与本次改动 diff 确认无关再继续）

- [ ] **Step 6.3: BE 启动手测**

Run: 启动后端（项目常规启动方式），`GET /api/v2/meta/user_group/view-config` 等常规接口 smoke；确认启动日志无 import 错误。
Expected: 正常

- [ ] **Step 6.4: Commit（如有零散修复）**

```bash
git add -A meta/services meta/tests
git commit -m "fix(spec20): regression fixes from full test run"
```

---

## Task 7: 迁移 v085 — 业务键 code 单列索引

**Files:**
- Create: `meta/migrations/v085__add_bizkey_code_indexes.py`

> 注意：Spec 19 预留的 v085「manager_id 删列」顺延为 v087+（本迁移先占 v085）。现有唯一索引 `(version_id, code)` 最左前缀不覆盖纯 `code IN (...)` 查询。

- [ ] **Step 7.1: 写迁移**（结构对齐 v083 的 up/verify/downgrade 惯例）

```python
# -*- coding: utf-8 -*-
"""
[v085 2026-09-06] Spec 20 业务键锚点: 为维度表 code 列建单列索引

背景: 锚点子查询 WHERE code IN (...) 无法利用 (version_id, code) 联合唯一索引
的最左前缀; 维度表 ≤ 数千行非瓶颈, 但索引廉价且随数据增长保平稳.

幂等: CREATE INDEX IF NOT EXISTS.
downgrade: DROP INDEX.
"""
import sqlite3

INDEXES = [
    ('idx_products_bizkey_code', 'products', 'code'),
    ('idx_versions_bizkey_code', 'versions', 'code'),
    ('idx_domains_bizkey_code', 'domains', 'code'),
    ('idx_sub_domains_bizkey_code', 'sub_domains', 'code'),
]


def up(conn: sqlite3.Connection):
    for name, table, col in INDEXES:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({col})")
    conn.commit()


def verify(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    names = {r[0] for r in cur.fetchall()}
    return all(name in names for name, _, _ in INDEXES)


def downgrade(conn: sqlite3.Connection):
    for name, _, _ in INDEXES:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
    conn.commit()
```

- [ ] **Step 7.2: 本地执行迁移 + 验证**

Run: `cd d:\filework\excel-to-diagram && python -c "import sqlite3; from meta.core.db_path import get_meta_db_path; conn=sqlite3.connect(get_meta_db_path()); from meta.migrations.v085__add_bizkey_code_indexes import up, verify; up(conn); print('verify:', verify(conn))"`
Expected: `verify: True`

- [ ] **Step 7.3: Commit**

```bash
git add meta/migrations/v085__add_bizkey_code_indexes.py
git commit -m "feat(spec20): v085 migration adds code-column indexes for bizkey anchors"
```

---

## Task 8: API 保存预检 + resolve-preview

**Files:**
- Modify: `meta/api/permission_set_dimension_scope_api.py`
- Test: `meta/tests/test_dim_scope_bizkey.py`（追加 API 用例）

- [ ] **Step 8.1: 写失败测试**

```python
class TestApiPreflight:
    def test_reject_injection_chars(self, db, monkeypatch):
        from meta.api.permission_set_dimension_scope_api import _validate_anchor_codes
        ok, err = _validate_anchor_codes(["SCM'; DROP TABLE x--"])
        assert not ok and '非法字符' in err

    def test_allow_normal_code(self):
        from meta.api.permission_set_dimension_scope_api import _validate_anchor_codes
        ok, err = _validate_anchor_codes(['SCM', 'SCM_PL-1.2'])
        assert ok and err == ''

    def test_unresolved_warning_not_blocking(self, db):
        from meta.api.permission_set_dimension_scope_api import _preflight_anchor_warnings
        warnings = _preflight_anchor_warnings(db, 1, 'domain', ['TYPO_X'])
        assert warnings and '未解析到' in warnings[0]
```

- [ ] **Step 8.2: 跑测试确认失败**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py::TestApiPreflight -v`
Expected: FAIL — ImportError

- [ ] **Step 8.3: 实现**（`permission_set_dimension_scope_api.py`，与 `_normalize_dim_values_to_ids` 并列）

```python
# [Spec 20] 业务键锚点白名单: 仅字母/数字/下划线/点/横线 (防 SQL 注入, 引擎侧另有转义双保险)
_ANCHOR_CODE_PATTERN = re.compile(r'^[A-Za-z0-9_.\-]+$')


def _validate_anchor_codes(values) -> tuple:
    """校验字符串锚点形态; 返回 (ok, err_msg)"""
    for v in values or []:
        if isinstance(v, str) and v.strip() != '*' \
                and not str(v).lstrip('-').isdigit():
            if not _ANCHOR_CODE_PATTERN.match(v.strip()):
                return False, f'业务键 "{v}" 含非法字符 (仅允许字母/数字/_/./-)'
    return True, ''


def _preflight_anchor_warnings(ds, permission_set_id, dim_code, anchor_codes):
    """[Spec 20] 保存预检: 锚点 0 命中 → warning (不阻塞, 允许先配权限后建对象)"""
    from meta.services.dimension_scope_engine import DimensionScopeEngine
    eng = DimensionScopeEngine(ds)
    resolved = eng._resolve_bizkeys(dim_code, list(anchor_codes))
    return [f'业务键 "{c}" 未解析到任何 {dim_code} 实例 (跨版本)'
            for c in anchor_codes if not resolved.get(c)]
```

（文件头补 `import re`。）POST 端点 `save_dimension_scopes`（:462）在 `_normalize_dim_values_to_ids`（:502）之后插入：

```python
                ok, err = _validate_anchor_codes(normalized_values)
                if not ok:
                    return jsonify({'success': False, 'message': err}), 400
                anchor_strs = [v for v in normalized_values
                               if isinstance(v, str) and v.strip() != '*'
                               and not str(v).lstrip('-').isdigit()]
                if anchor_strs:
                    warns = _preflight_anchor_warnings(
                        ds, permission_set_id,
                        item.get('dimension_code'), anchor_strs)
                    preflight_warnings.extend(warns)
```

（`preflight_warnings = []` 在循环前初始化；响应 JSON 追加 `'warnings': preflight_warnings`。）

resolve-preview 端点（同文件 POST 路由之后追加）：

```python
@role_dim_bp.route('/<int:permission_set_id>/dimension-scopes/resolve-preview',
                   methods=['POST'])
def resolve_dim_scope_preview(permission_set_id):
    """[Spec 20] 锚点解析预览: 返回每个业务键当前命中的实例 (跨版本)"""
    payload = request.get_json(silent=True) or {}
    results = {}
    ds = _get_ds()
    from meta.services.dimension_scope_engine import DimensionScopeEngine
    eng = DimensionScopeEngine(ds)
    for item in payload.get('scopes', []):
        dim = item.get('dimension_code')
        codes = [v for v in item.get('dimension_values', [])
                 if isinstance(v, str) and v.strip() != '*'
                 and not str(v).lstrip('-').isdigit()]
        if not dim or not codes:
            continue
        resolved = eng._resolve_bizkeys(dim, codes)
        dim_results = {}
        for c in codes:
            ids = sorted(resolved.get(c) or [])
            entries = []
            for i in ids:
                row = ds.execute(
                    f"SELECT d.code, d.name, v.code FROM {RESOURCE_TABLE_MAP[dim]} d "
                    f"LEFT JOIN versions v ON d.version_id = v.id WHERE d.id = ?",
                    [i]).fetchone()
                entries.append({'id': i, 'code': row[0] if row else None,
                                'name': row[1] if row else None,
                                'version': row[2] if row else None})
            dim_results[c] = {
                'resolved_count': len(ids),
                'instances': entries,
                **({'warning': '未解析到实例'} if not ids else {}),
            }
        results[dim] = dim_results
    return jsonify({'success': True, 'data': results})
```

（`RESOURCE_TABLE_MAP` 按文件现有 import 惯例补；`_get_ds` / `role_dim_bp` 用文件内既有名称——实施时以文件实际 helper 名为准，grep `def _get` 定位。）

- [ ] **Step 8.4: 跑测试确认通过**

Run: `cd d:\filework\excel-to-diagram && python -m pytest meta/tests/test_dim_scope_bizkey.py -v`
Expected: 全 PASS

- [ ] **Step 8.5: Commit**

```bash
git add meta/api/permission_set_dimension_scope_api.py meta/tests/test_dim_scope_bizkey.py
git commit -m "feat(spec20): anchor preflight validation + resolve-preview endpoint"
```

---

## Task 9: 前端业务键模式（P3，框架）

**Files:** 权限集编辑 · 数据范围 · 维度值选择器组件（实施时 grep `dimension-scopes` 定位 `src/views` 下组件）

- [ ] **Step 9.1**: 定位选择器组件（`grep -r "dimension-scopes" src/ --include=*.vue --include=*.js`）
- [ ] **Step 9.2**: 保存请求对业务键实体提供「跨版本（业务键）/ 仅此实例（ID）」切换，默认业务键；提交值由对象 `{code,id,name}` 改为可提交字符串 code（后端 `_normalize_dim_values_to_ids` 已放行字符串）
- [ ] **Step 9.3**: 已存字符串值回显 `code（名称 · 当前命中 N 个实例）`，数据来自 `POST /dimension-scopes/resolve-preview`；`resolved_count=0` 红色警示
- [ ] **Step 9.4**: Vitest 组件测试 + 手测：配置 `SCM` → 三产品下供应链云全部可见
- [ ] **Step 9.5**: Commit `feat(spec20): frontend bizkey anchor mode for dimension scope editor`

---

## Task 10: 收尾

- [ ] **Step 10.1**: 全量测试 `python -m pytest meta/tests/test_dim_scope_bizkey.py meta/tests/test_dim_scope_conflict.py meta/tests/test_intent_scope_adapter.py -v` 全绿
- [ ] **Step 10.2**: 手动验收（对照 Spec §7）：BE 重启 → 权限集配 domain=`["SCM"]` → 用绑定用户查列表可见多版本 SCM → 新建版本+同 code 域（**不 re-derive**）→ 刷新直接可见
- [ ] **Step 10.3**: 更新 Spec 20 状态 Draft → Implemented（附验收证据）
- [ ] **Step 10.4**: 最终 commit

---

## Self-Review 结论

- **Spec 覆盖**：G1→Task 1/2/3/4；G2→Task 5（铁证）；G3→Task 2（failed 标记）+ Task 4（1=0 落点）；G4→Task 4.1 golden + Task 6 回归；G5→Task 1 开关（OFF=fail-closed）；4.5 API→Task 8；4.6 前端→Task 9；§7 测试计划→各 Task。✅
- **占位符扫描**：Task 9 为 P3 框架任务（Spec 分期如此约定，组件未定位无法给真实代码——已在步骤中给出定位命令与验收判据）；其余任务无 TBD/TODO。⚠️ 已知妥协点，P3 启动时补细化。
- **类型一致性**：`expand_dimension_values_detail` 五元组在 Task 2 定义、Task 4 消费一致；`_build_chain_condition(anchor_codes=...)` Task 3 定义、Task 4 调用一致；`_resolve_bizkeys` 返回 `Dict[str, Set[int]]` 三处使用一致。✅

## 回滚方案

- 运行时：`DIM_SCOPE_BIZKEY_ENABLED=0` → 锚点一律 `1=0`（绝不放大），数字路径不受影响。
- 代码：revert Task 1-4 的提交即可（`expand_dimension_values` 对外签名未变，无调用方改动）。
- 迁移 v085：`downgrade(conn)` DROP INDEX。
