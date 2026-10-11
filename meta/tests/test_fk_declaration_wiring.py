# -*- coding: utf-8 -*-
"""外键声明落库接线测试 (2026-10-11)

依据: 主数据系统性检查报告 §五 M1 · §六 / 蓝图 §5.3.2

根因（两个静默丢弃点，均无报错无告警）:
  ① [schema_generator.py L70-72] `type: reference` 未声明 `source_field`
     ⇒ `continue` 丢弃（REFERENCE 必须显式声明 FK 列）
  ② [SchemaMigrator.migrate L407-421] 表已存在时**只走 ADD COLUMN 分支**，
     没有任何 FK 增量路径；而 `CREATE TABLE IF NOT EXISTS` 对已存在表是 no-op
     ⇒ 表建好后新增的 relations 声明**永远不会**落成真 FK
     （2026-10-11 实测: calc_results 2 处 / change_events 1 / change_subscriptions 1）

本测试锁定:
  ① 静态规则: reference + cardinality ∈ (N:1,1:1) 必须声明 source_field
     （修复前 relationship 的 rel_to_source_bo / rel_to_target_bo 2 条命中）
  ② drift: 生成器会声明的 FK 必须已存在于真实 DB —— 防「声明未落库」复发
  ③ 已修复的 4 处 FK 结构性存在（端到端回归）
"""
import os
import sqlite3
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, _PROJECT_ROOT)

_META_DIR = os.path.join(_PROJECT_ROOT, 'meta')
_SCHEMA_DIR = os.path.join(_META_DIR, 'schemas')
_REAL_DB = os.path.join(_META_DIR, 'architecture.db')


def _load_objects():
    from meta.core.yaml_loader import load_yaml_directory
    return load_yaml_directory(_SCHEMA_DIR)


def _declared_fk_columns(obj):
    """复刻落库器口径：返回该对象「应当落成 FK」的列集合。"""
    from meta.core.yaml_loader import RelationType
    cols = set()
    for r in obj.relations:
        if r.relation_type not in (RelationType.PARENT_CHILD,
                                   RelationType.REFERENCE):
            continue
        if r.relation_type == RelationType.REFERENCE and not r.source_field:
            continue
        if r.cardinality not in ('N:1', '1:1'):
            continue
        cols.add(r.source_field or f'{r.target_object}_id')
    return cols


def _actual_fk_columns(cur, table):
    return {f[3] for f in cur.execute(f'PRAGMA foreign_key_list("{table}")')}


# ────────────────────────────────────────
# ① 静态规则：reference + N:1/1:1 必须声明 source_field
# ────────────────────────────────────────
class TestReferenceRequiresSourceField:
    def test_no_reference_relation_missing_source_field(self):
        """reference 且 cardinality ∈ (N:1,1:1) 却缺 source_field ⇒ 会被静默丢弃

        落库器 schema_generator.py L71: REFERENCE 无 source_field 即 continue。
        该条件在真实 schema 中必须为 0（修复前 relationship 2 条命中）。
        """
        from meta.core.yaml_loader import RelationType
        offenders = []
        for o in _load_objects():
            for r in o.relations:
                if (r.relation_type == RelationType.REFERENCE
                        and r.cardinality in ('N:1', '1:1')
                        and not r.source_field):
                    offenders.append(f'{o.id}.{r.id}→{r.target_object}')
        assert offenders == [], (
            'reference 关系缺 source_field（会被落库器静默丢弃）: '
            f'{offenders}')

    def test_relationship_bo_relations_have_source_field(self):
        """回归: relationship 的两个 BO 引用已补 source_field（原缺失）"""
        rel = next(o for o in _load_objects() if o.id == 'relationship')
        by_id = {r.id: r for r in rel.relations}
        assert by_id['rel_to_source_bo'].source_field == 'source_bo_id'
        assert by_id['rel_to_target_bo'].source_field == 'target_bo_id'


# ────────────────────────────────────────
# ② drift：声明了 FK 就必须在真实 DB 里存在
# ────────────────────────────────────────
@pytest.mark.integration
class TestDeclaredFkLandsInDb:
    @staticmethod
    def _conn():
        if not os.path.exists(_REAL_DB):
            pytest.skip(f'真实 DB 不存在: {_REAL_DB}')
        return sqlite3.connect(f'file:{_REAL_DB}?mode=ro', uri=True)

    def test_no_declared_fk_missing_in_db(self):
        """drift 护栏: 任何「声明了却未落库」的 FK 都必须使本测试失败

        这是 A 类缺陷（表已存在 ⇒ 迁移器无 FK 增量路径）的回归网。
        2026-10-11 修复前: calc_results(2) / change_events(1) /
        change_subscriptions(1) 共 4 处命中；修复后 0。
        """
        conn = self._conn()
        cur = conn.cursor()
        tables = {r[0] for r in cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'")}
        gaps = []
        for o in _load_objects():
            if not o.table_name or o.table_name not in tables:
                continue
            declared = _declared_fk_columns(o)
            missing = declared - _actual_fk_columns(cur, o.table_name)
            if missing:
                gaps.append(f'{o.id}({o.table_name}): {sorted(missing)}')
        conn.close()
        assert gaps == [], f'声明了但 DB 未落的 FK: {gaps}'

    @pytest.mark.parametrize('table,cols', [
        ('calc_results', ['external_rate_source_id', 'pricing_period_id']),
        ('change_events', ['audit_log_id']),
        ('change_subscriptions', ['user_id']),
    ])
    def test_fixed_fk_present(self, table, cols):
        """回归: 2026-10-11 补落的 4 处 FK 必须存在"""
        conn = self._conn()
        actual = _actual_fk_columns(conn.cursor(), table)
        conn.close()
        missing = [c for c in cols if c not in actual]
        assert missing == [], f'{table} 缺 FK: {missing}（实际 {sorted(actual)}）'


# ────────────────────────────────────────
# ③ 落库器口径守护（不变式，防改动误伤）
# ────────────────────────────────────────
class TestGeneratorFkCriteria:
    def test_generator_matches_declared_columns(self, tmp_path):
        """用 tmp DB 走 CREATE TABLE 路径: 生成器产出的 FK 列 == 口径函数结果

        确保 _declared_fk_columns 与 schema_generator 的实际行为一致
        （若生成器口径变化，本测试失败从而提醒更新护栏）。
        """
        import re
        from meta.core.schema_generator import SchemaGenerator
        gen = SchemaGenerator()
        mismatches = []
        for o in _load_objects():
            if not o.table_name:
                continue
            from meta.core.models import ObjectType
            if o.object_type != ObjectType.ENTITY:
                continue
            sql = gen.generate_create_table(o)
            emitted = set(re.findall(r'FOREIGN KEY \("?(\w+)"?\)', sql or ''))
            declared = _declared_fk_columns(o)
            if emitted != declared:
                mismatches.append(
                    f'{o.id}: 生成器={sorted(emitted)} 口径={sorted(declared)}')
        assert mismatches == [], (
            '生成器 FK 口径与护栏函数不一致（护栏需同步更新）: ' + '; '.join(
                mismatches[:5]))