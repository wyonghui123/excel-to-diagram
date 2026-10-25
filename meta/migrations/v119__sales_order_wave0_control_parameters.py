# -*- coding: utf-8 -*-
"""[v119 2026-10-25] 销售订单波次 0：控制参数补齐（3 条定义 + 4 条取值）

依据:
  docs/superpowers/specs/2026-10-24-sales-order-wave0-detailed-plan.md §2.2

范围:
  新增定义 3 条（domain='sales'）
    qty_required       bool    true    行必须录数量
    price_required     bool    true    行必须录单价
    default_incoterm   string  空      贸易条款兜底
  新增取值 4 条（维度只用 line_type_id，其余维度留空，specificity_rank=100）
    qty_required      + TXT  = false
    price_required    + TXT  = false
    price_required    + FOC  = false
    pricing_relevant  + TXT  = false   （pricing_relevant 定义已存在，本迁移只补取值）

边界:
  只处理上述 7 条，不重跑整份销售配置种子（meta/scripts/init_sales_config_seed.py）
  —— 该脚本还含税务参数，超出波次 0 口径。

幂等:
  定义按 code 判存在；取值按 (参数 id, line_type_id, 其余维度 IS NULL, rank=100) 判存在。
  已存在则只刷新值 / 说明，不重置 status。

回滚:
  删除本迁移创建的 4 条取值，再删除 3 条定义（仅当该定义下已无取值）。
"""
import sqlite3
from pathlib import Path

PARAM_DEFS = (
    ('qty_required', '行数量必录', 'bool', 'true',
     '单据行是否必须录入数量；文本行按行类型置 false'),
    ('price_required', '行单价必录', 'bool', 'true',
     '单据行是否必须录入单价；免费行 / 文本行按行类型置 false'),
    ('default_incoterm', '默认贸易条款', 'string', None,
     '单据类型与客户账户都未给贸易条款时的兜底代码（Incoterms 2020 三字码）'),
)

#: (参数编码, 行类型编码, 取值, 说明)
PARAM_VALUES = (
    ('qty_required', 'TXT', 'false', '文本行无数量'),
    ('price_required', 'TXT', 'false', '文本行无单价'),
    ('price_required', 'FOC', 'false', '免费行单价为 0'),
    ('pricing_relevant', 'TXT', 'false', '文本行不参与定价'),
)

SCOPE_BO = 'sales_order'
RANK = 100


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _param_id(conn, code):
    row = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code = ?', (code,)
    ).fetchone()
    return row[0] if row else None


def _line_type_id(conn, code):
    row = conn.execute(
        "SELECT id FROM type_definitions "
        "WHERE scope_bo = ? AND level = 'line' AND code = ?", (SCOPE_BO, code)
    ).fetchone()
    return row[0] if row else None


def _value_id(conn, param_id, line_type_id):
    row = conn.execute(
        'SELECT id FROM control_parameter_values '
        'WHERE control_parameter_id = ? AND line_type_id = ? '
        "  AND org_id IS NULL AND document_type_id IS NULL "
        "  AND item_group_id IS NULL AND specificity_rank = ?",
        (param_id, line_type_id, RANK)
    ).fetchone()
    return row[0] if row else None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v119] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v119] 开始: 销售订单波次 0 控制参数')
        if not _table_exists(conn, 'control_parameter_defs'):
            print('[v119] 缺少 control_parameter_defs，跳过')
            return False

        # 1) 定义
        for code, name, value_type, default_value, desc in PARAM_DEFS:
            if _param_id(conn, code):
                conn.execute(
                    'UPDATE control_parameter_defs SET name = ?, '
                    'default_value = ?, description = ?, status = ? WHERE code = ?',
                    (name, default_value, desc, 'active', code))
                print('  ~ UPDATE def %s' % code)
            else:
                conn.execute(
                    'INSERT INTO control_parameter_defs '
                    '(code, name, domain, value_type, target_bo, default_value, '
                    ' status, description, created_at) '
                    "VALUES (?, ?, 'sales', ?, NULL, ?, 'active', ?, datetime('now'))",
                    (code, name, value_type, default_value, desc))
                print('  + INSERT def %s' % code)

        # 2) 取值
        for param_code, line_code, value, desc in PARAM_VALUES:
            param_id = _param_id(conn, param_code)
            line_id = _line_type_id(conn, line_code)
            if not param_id or not line_id:
                print('  ! 跳过取值 %s/%s：参数或行类型缺失' % (param_code, line_code))
                continue
            existing = _value_id(conn, param_id, line_id)
            if existing:
                conn.execute(
                    'UPDATE control_parameter_values SET value = ?, description = ?, '
                    "status = 'active' WHERE id = ?", (value, desc, existing))
                print('  ~ UPDATE value %s/%s' % (param_code, line_code))
            else:
                conn.execute(
                    'INSERT INTO control_parameter_values '
                    '(control_parameter_id, line_type_id, specificity_rank, value, '
                    ' status, description, created_at) '
                    "VALUES (?, ?, ?, ?, 'active', ?, datetime('now'))",
                    (param_id, line_id, RANK, value, desc))
                print('  + INSERT value %s/%s' % (param_code, line_code))

        conn.commit()
        print('[v119] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v119] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v119 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing_defs = [c for c, *_ in PARAM_DEFS if not _param_id(conn, c)]
        if missing_defs:
            print('[v119 verify] FAIL: 定义缺失 %s' % missing_defs)
            return False
        missing_values = []
        for param_code, line_code, _, _ in PARAM_VALUES:
            param_id = _param_id(conn, param_code)
            line_id = _line_type_id(conn, line_code)
            if not param_id or not line_id or not _value_id(conn, param_id, line_id):
                missing_values.append('%s/%s' % (param_code, line_code))
        if missing_values:
            print('[v119 verify] FAIL: 取值缺失 %s' % missing_values)
            return False
        print('[v119 verify] OK: 3 条定义 + 4 条取值已就位')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v119 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for param_code, line_code, _, _ in PARAM_VALUES:
            param_id = _param_id(conn, param_code)
            line_id = _line_type_id(conn, line_code)
            if not param_id or not line_id:
                continue
            value_id = _value_id(conn, param_id, line_id)
            if value_id:
                conn.execute(
                    'DELETE FROM control_parameter_values WHERE id = ?', (value_id,))
                print('  - DELETE value %s/%s' % (param_code, line_code))
        for code, *_ in PARAM_DEFS:
            param_id = _param_id(conn, code)
            if not param_id:
                continue
            remain = conn.execute(
                'SELECT COUNT(*) FROM control_parameter_values '
                'WHERE control_parameter_id = ?', (param_id,)).fetchone()[0]
            if remain:
                print('  ! 定义 %s 仍有 %s 条取值，保留' % (code, remain))
                continue
            conn.execute(
                'DELETE FROM control_parameter_defs WHERE id = ?', (param_id,))
            print('  - DELETE def %s' % code)
        conn.commit()
        print('[v119 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v119 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else get_meta_db_path()
    if '--rollback' in sys.argv:
        rollback(db)
    else:
        migrate(db)
        verify(db)
