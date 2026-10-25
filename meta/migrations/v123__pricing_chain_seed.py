# -*- coding: utf-8 -*-
"""[v123] 销售订单波次 1 W1-A：定价链种子点亮

依据:
  docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
    §3.3 种子规格（8 类）
    §3.2 数据链（因子 → 键 → 序列 → 类型 → 价目表 → 记录 → 过程 → 步骤）

范围:
  1. factor_catalogs  3 条（物料 / 销售组织 / 客户）
  2. key_schemas      KS_ITEM（key_fields=["item_id"]）
  3. lookup_sequences LK_ITEM_STD（单槽位 → KS_ITEM）
  4. rate_types       RT_LIST_PRICE
  5. calc_procedures  PRICE_STD
  6. calc_procedure_steps  seq=10 取价 / seq=20 取整
  7. rate_tables      PL_STD（approved / CNY / 全局共享）
  8. rate_records     PT_ITEM_<item_id>（示例单价，缺物料则跳过）
  9. pricing_determinations  PD_STD（组织/类型/币种全通配的兜底规则）

与 Spec §3.3 的两处口径修正（以引擎实现为准）:
  1. factor_catalog.source_type 用 `static`，不用 `field` —— 本表枚举只有
     static / master / quality / measurement / market；`item_id` / `sales_org_id`
     取自单据自身，正属 static 语义（`field` 取值在枚举中不存在）。
  2. seq=10 用 `formula` + `{"expr": "lookup_amount * base"}`，不用
     `list_price` + `{"rate_source": "rate_record"}` —— 依据引擎契约：
       `calc_procedure_executor._op_list_price` 只读 `params["rate"]`，
       查表命中不会写进步骤 params，故该写法恒算出 0；
       `lookup_resolver` 产出的 `lookup_amount` 是**费率**（每 1 个的单价，
       含 rate_qty 折算），不是金额，故须再乘计算基 `base`（= 行数量）
       才是行金额——与 §3.7「unit_price = net_amount / qty」闭合。

幂等:
  全部按业务键判存在，已存在则 SKIP（整包复跑第二次应全部 SKIP，不刷新已配数据）。

回滚:
  按依赖倒序删除 rate_records → calc_procedure_steps → rate_tables →
  calc_procedures → rate_types → lookup_sequences → key_schemas → factor_catalogs。
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

#: (object_type, field_id, source_type, is_price_relevant, description)
FACTORS = (
    ('sales_order_line', 'item_id', 'static', 1, '物料：行级取价主维度'),
    ('sales_order', 'sales_org_id', 'static', 1, '销售组织：价目表作用域维度（二期键使用）'),
    ('sales_order', 'customer_account_id', 'static', 1, '客户：客户级价目（二期键使用）'),
)

KEY_SCHEMA_CODE = 'KS_ITEM'
KEY_SCHEMA_NAME = '物料匹配键'
KEY_SCHEMA_FIELDS = ['item_id']

SEQUENCE_CODE = 'LK_ITEM_STD'
SEQUENCE_NAME = '物料标准查找序列'

RATE_TYPE_CODE = 'RT_LIST_PRICE'
RATE_TYPE_NAME = '标准单价'

PROCEDURE_CODE = 'PRICE_STD'
PROCEDURE_NAME = '标准销售定价过程'

#: (seq, element_type, rate_type_code, params, description)
STEPS = (
    (10, 'formula', RATE_TYPE_CODE, {'expr': 'lookup_amount * base'},
     '按匹配键取标准单价，并按计算基（行数量）放大为行金额'),
    (20, 'round', None, {'mode': 'round', 'digits': 2},
     '按两位小数取整，仅用于展示/入账，不参与累加'),
)

RATE_TABLE_CODE = 'PL_STD'
RATE_TABLE_NAME = '标准价目表'
RATE_TABLE_CURRENCY = 'CNY'

#: (item_id, 示例单价)
RATE_RECORDS = (
    (1, 8.00),
    (2, 12.50),
)

#: 兜底确定规则：组织/类型/币种全通配，唯一一条，seq 靠后（空维度即天然兜底）
DETERMINATION_CODE = 'PD_STD'
DETERMINATION_NAME = '标准定价确定规则'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _one(conn, sql, params):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _factor_exists(conn, object_type, field_id):
    return _one(conn, 'SELECT id FROM factor_catalogs WHERE object_type = ? AND field_id = ?',
                (object_type, field_id)) is not None


def _by_code(conn, table, code):
    return _one(conn, 'SELECT code FROM %s WHERE code = ?' % table, (code,))


def _code_id(conn, table, code):
    return _one(conn, 'SELECT id FROM %s WHERE code = ?' % table, (code,))


def _step_exists(conn, procedure_id, seq):
    return _one(conn, 'SELECT id FROM calc_procedure_steps '
                      'WHERE calc_procedure_id = ? AND seq = ?',
                (procedure_id, seq)) is not None


def _item_exists(conn, item_id):
    return _one(conn, 'SELECT id FROM items WHERE id = ?', (item_id,)) is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v123] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v123] 开始: 定价链种子点亮')
        required = ('factor_catalogs', 'key_schemas', 'lookup_sequences',
                    'rate_types', 'calc_procedures', 'calc_procedure_steps',
                    'rate_tables', 'rate_records', 'items')
        missing = [t for t in required if not _table_exists(conn, t)]
        if missing:
            print('[v123] 缺少表 %s，终止' % missing)
            return False

        now = "datetime('now')"

        # 1) 因子目录
        for object_type, field_id, source_type, relevant, desc in FACTORS:
            if _factor_exists(conn, object_type, field_id):
                print('  SKIP factor %s/%s' % (object_type, field_id))
                continue
            conn.execute(
                'INSERT INTO factor_catalogs '
                '(object_type, field_id, source_type, is_price_relevant, '
                ' description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, %s, %s)' % (now, now),
                (object_type, field_id, source_type, relevant, desc))
            print('  + INSERT factor %s/%s' % (object_type, field_id))

        # 2) 匹配键表
        if _by_code(conn, 'key_schemas', KEY_SCHEMA_CODE):
            print('  SKIP key_schema %s' % KEY_SCHEMA_CODE)
        else:
            conn.execute(
                'INSERT INTO key_schemas '
                '(code, name, key_fields, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (KEY_SCHEMA_CODE, KEY_SCHEMA_NAME, json.dumps(KEY_SCHEMA_FIELDS),
                 '按物料匹配标准单价'))
            print('  + INSERT key_schema %s' % KEY_SCHEMA_CODE)
        key_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)

        # 3) 查找序列（单槽位）
        if _by_code(conn, 'lookup_sequences', SEQUENCE_CODE):
            print('  SKIP lookup_sequence %s' % SEQUENCE_CODE)
        else:
            steps = [{'seq': 1, 'key_schema_id': key_schema_id}]
            conn.execute(
                'INSERT INTO lookup_sequences '
                '(code, name, steps, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (SEQUENCE_CODE, SEQUENCE_NAME, json.dumps(steps),
                 '首槽位按物料键查价目行'))
            print('  + INSERT lookup_sequence %s' % SEQUENCE_CODE)
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)

        # 4) 费率类型
        if _by_code(conn, 'rate_types', RATE_TYPE_CODE):
            print('  SKIP rate_type %s' % RATE_TYPE_CODE)
        else:
            conn.execute(
                'INSERT INTO rate_types '
                '(code, name, rate_class, calc_type, rate_source, sign, rounding, '
                ' numeric_field, display_scale, exclusion_group_id, manual_allowed, '
                ' mandatory, statistical, lookup_sequence_id, description, '
                ' created_at, updated_at) '
                "VALUES (?, ?, 'price', 'fixed', 'rate_record', '+', 'round', "
                " 'unit_price', '2', NULL, 1, 0, 0, ?, ?, %s, %s)" % (now, now),
                (RATE_TYPE_CODE, RATE_TYPE_NAME, sequence_id,
                 '标准单价：取价目行的费率，允许在单据上手工覆盖'))
            print('  + INSERT rate_type %s' % RATE_TYPE_CODE)
        rate_type_id = _code_id(conn, 'rate_types', RATE_TYPE_CODE)

        # 5) 定价过程
        if _by_code(conn, 'calc_procedures', PROCEDURE_CODE):
            print('  SKIP calc_procedure %s' % PROCEDURE_CODE)
        else:
            conn.execute(
                'INSERT INTO calc_procedures '
                '(code, name, procedure_type, result_semantic, currency, '
                ' subtotal_keys, description, created_at, updated_at) '
                "VALUES (?, ?, 'pricing', 'price', NULL, '[]', ?, %s, %s)"
                % (now, now),
                (PROCEDURE_CODE, PROCEDURE_NAME,
                 '标准销售定价过程：查表得单价 → 按数量放大 → 取整'))
            print('  + INSERT calc_procedure %s' % PROCEDURE_CODE)
        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)

        # 6) 计算步骤
        for seq, element_type, rate_type_code, params, desc in STEPS:
            if _step_exists(conn, procedure_id, seq):
                print('  SKIP calc_procedure_step %s/%s'
                      % (PROCEDURE_CODE, seq))
                continue
            step_rate_type_id = (_code_id(conn, 'rate_types', rate_type_code)
                                 if rate_type_code else None)
            conn.execute(
                'INSERT INTO calc_procedure_steps '
                '(calc_procedure_id, seq, element_type, rate_type_id, condition, '
                ' params, rolling, base_step, subtotal_key, description, '
                ' created_at, updated_at) '
                'VALUES (?, ?, ?, ?, NULL, ?, 0, NULL, NULL, ?, %s, %s)'
                % (now, now),
                (procedure_id, seq, element_type, step_rate_type_id,
                 json.dumps(params), desc))
            print('  + INSERT calc_procedure_step %s/%s'
                  % (PROCEDURE_CODE, seq))

        # 7) 价目表
        if _by_code(conn, 'rate_tables', RATE_TABLE_CODE):
            print('  SKIP rate_table %s' % RATE_TABLE_CODE)
        else:
            conn.execute(
                'INSERT INTO rate_tables '
                '(code, name, type, currency, owner_org_id, status, description, '
                ' created_at, updated_at) '
                "VALUES (?, ?, 'standard', ?, NULL, 'approved', ?, %s, %s)"
                % (now, now),
                (RATE_TABLE_CODE, RATE_TABLE_NAME, RATE_TABLE_CURRENCY,
                 '全局共享标准价目表（不限定销售组织）'))
            print('  + INSERT rate_table %s' % RATE_TABLE_CODE)
        rate_table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)

        # 8) 价目行（缺物料则跳过）
        today = date.today().isoformat()
        for item_id, rate in RATE_RECORDS:
            code = 'PT_ITEM_%s' % item_id
            if _by_code(conn, 'rate_records', code):
                print('  SKIP rate_record %s' % code)
                continue
            if not _item_exists(conn, item_id):
                print('[v123] 缺少物料 %s，跳过价目行种子' % item_id)
                continue
            conn.execute(
                'INSERT INTO rate_records '
                '(code, rate_table_id, key_schema_id, keys, rate_type_id, rate, '
                ' value, valid_from, valid_to, currency, rate_unit, rate_qty, '
                ' scale, scale_semantic, scale_divisor, exclude_bo, hit_policy, '
                ' allocation_weight, priority, status, description, '
                ' created_at, updated_at) '
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, NULL, NULL, NULL, 1, "
                " NULL, NULL, NULL, NULL, 'exclusive', NULL, 100, 'active', ?, "
                " %s, %s)" % (now, now),
                (code, rate_table_id, key_schema_id,
                 json.dumps({'item_id': item_id}), rate_type_id, rate,
                 today, '物料 %s 的标准单价' % item_id))
            print('  + INSERT rate_record %s' % code)

        # 9) 确定规则（兜底：组织 / 类型 / 币种全通配）
        if _by_code(conn, 'pricing_determinations', DETERMINATION_CODE):
            print('  SKIP pricing_determination %s' % DETERMINATION_CODE)
        else:
            conn.execute(
                'INSERT INTO pricing_determinations '
                '(code, name, sales_org_id, order_type_id, rate_table_id, '
                ' calc_procedure_id, lookup_sequence_id, currency, seq, '
                ' valid_from, valid_to, status, description, '
                ' created_at, updated_at) '
                "VALUES (?, ?, NULL, NULL, ?, ?, ?, NULL, 100, NULL, NULL, "
                " 'active', ?, %s, %s)" % (now, now),
                (DETERMINATION_CODE, DETERMINATION_NAME, rate_table_id,
                 procedure_id, sequence_id,
                 '全组织、全单据类型沿用标准价目表与标准定价过程'))
            print('  + INSERT pricing_determination %s' % DETERMINATION_CODE)

        conn.commit()
        print('[v123] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v123] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v123 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        missing_factors = [(o, f) for o, f, *_ in FACTORS
                           if not _factor_exists(conn, o, f)]
        if missing_factors:
            print('[v123 verify] FAIL: 因子缺失 %s' % missing_factors)
            return False

        key_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
        if not key_schema_id:
            print('[v123 verify] FAIL: 匹配键 %s 缺失' % KEY_SCHEMA_CODE)
            return False

        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
        if not sequence_id:
            print('[v123 verify] FAIL: 查找序列 %s 缺失' % SEQUENCE_CODE)
            return False
        raw_steps = _one(conn, 'SELECT steps FROM lookup_sequences WHERE id = ?',
                         (sequence_id,))
        try:
            slots = json.loads(raw_steps or '[]')
        except (TypeError, ValueError):
            slots = []
        if not slots or slots[0].get('key_schema_id') != key_schema_id:
            print('[v123 verify] FAIL: 查找序列槽位未指向 %s' % KEY_SCHEMA_CODE)
            return False

        rate_type_id = _code_id(conn, 'rate_types', RATE_TYPE_CODE)
        if not rate_type_id:
            print('[v123 verify] FAIL: 费率类型 %s 缺失' % RATE_TYPE_CODE)
            return False
        bound_seq = _one(conn, 'SELECT lookup_sequence_id FROM rate_types WHERE id = ?',
                         (rate_type_id,))
        if bound_seq != sequence_id:
            print('[v123 verify] FAIL: 费率类型未挂查找序列 %s' % SEQUENCE_CODE)
            return False

        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
        if not procedure_id:
            print('[v123 verify] FAIL: 定价过程 %s 缺失' % PROCEDURE_CODE)
            return False
        step_rows = conn.execute(
            'SELECT seq, element_type FROM calc_procedure_steps '
            'WHERE calc_procedure_id = ? ORDER BY seq', (procedure_id,)
        ).fetchall()
        expected = [(seq, element_type) for seq, element_type, *_ in STEPS]
        if [(r[0], r[1]) for r in step_rows] != expected:
            print('[v123 verify] FAIL: 过程步骤不符 %s' % (step_rows,))
            return False

        rate_table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
        if not rate_table_id:
            print('[v123 verify] FAIL: 价目表 %s 缺失' % RATE_TABLE_CODE)
            return False
        table_row = conn.execute(
            'SELECT status, currency, owner_org_id FROM rate_tables WHERE id = ?',
            (rate_table_id,)).fetchone()
        if table_row != ('approved', RATE_TABLE_CURRENCY, None):
            print('[v123 verify] FAIL: 价目表状态/币种/作用域不符 %s' % (table_row,))
            return False

        # 每个存在的物料都应有可被 load_candidates 取到的价目行
        for item_id, _rate in RATE_RECORDS:
            if not _item_exists(conn, item_id):
                continue
            code = 'PT_ITEM_%s' % item_id
            row = conn.execute(
                'SELECT rate, keys, status FROM rate_records WHERE code = ?',
                (code,)).fetchone()
            if not row:
                print('[v123 verify] FAIL: 价目行 %s 缺失' % code)
                return False
            if row[2] != 'active':
                print('[v123 verify] FAIL: 价目行 %s 非 active' % code)
                return False
            if json.loads(row[1] or '{}').get('item_id') != item_id:
                print('[v123 verify] FAIL: 价目行 %s 键值不符' % code)
                return False

        rule = conn.execute(
            'SELECT rate_table_id, calc_procedure_id, lookup_sequence_id, status '
            'FROM pricing_determinations WHERE code = ?', (DETERMINATION_CODE,)
        ).fetchone()
        if not rule:
            print('[v123 verify] FAIL: 确定规则 %s 缺失' % DETERMINATION_CODE)
            return False
        if rule != (rate_table_id, procedure_id, sequence_id, 'active'):
            print('[v123 verify] FAIL: 确定规则指向不符 %s' % (rule,))
            return False

        print('[v123 verify] OK: 3 因子 + KS_ITEM + LK_ITEM_STD + RT_LIST_PRICE '
              '+ PRICE_STD(2 步) + PL_STD(approved/CNY) + 价目行 + PD_STD')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v123 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _by_code(conn, 'pricing_determinations', DETERMINATION_CODE):
            conn.execute('DELETE FROM pricing_determinations WHERE code = ?',
                         (DETERMINATION_CODE,))
            print('  - DELETE pricing_determination %s' % DETERMINATION_CODE)

        for item_id, _rate in RATE_RECORDS:
            code = 'PT_ITEM_%s' % item_id
            if _by_code(conn, 'rate_records', code):
                conn.execute('DELETE FROM rate_records WHERE code = ?', (code,))
                print('  - DELETE rate_record %s' % code)

        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
        if procedure_id:
            conn.execute('DELETE FROM calc_procedure_steps WHERE calc_procedure_id = ?',
                         (procedure_id,))

        if _by_code(conn, 'rate_tables', RATE_TABLE_CODE):
            conn.execute('DELETE FROM rate_tables WHERE code = ?', (RATE_TABLE_CODE,))
            print('  - DELETE rate_table %s' % RATE_TABLE_CODE)
        if procedure_id:
            conn.execute('DELETE FROM calc_procedures WHERE id = ?', (procedure_id,))
            print('  - DELETE calc_procedure %s' % PROCEDURE_CODE)
        if _by_code(conn, 'rate_types', RATE_TYPE_CODE):
            conn.execute('DELETE FROM rate_types WHERE code = ?', (RATE_TYPE_CODE,))
            print('  - DELETE rate_type %s' % RATE_TYPE_CODE)
        if _by_code(conn, 'lookup_sequences', SEQUENCE_CODE):
            conn.execute('DELETE FROM lookup_sequences WHERE code = ?', (SEQUENCE_CODE,))
            print('  - DELETE lookup_sequence %s' % SEQUENCE_CODE)
        if _by_code(conn, 'key_schemas', KEY_SCHEMA_CODE):
            conn.execute('DELETE FROM key_schemas WHERE code = ?', (KEY_SCHEMA_CODE,))
            print('  - DELETE key_schema %s' % KEY_SCHEMA_CODE)
        for object_type, field_id, *_ in FACTORS:
            if _factor_exists(conn, object_type, field_id):
                conn.execute('DELETE FROM factor_catalogs '
                             'WHERE object_type = ? AND field_id = ?',
                             (object_type, field_id))
                print('  - DELETE factor %s/%s' % (object_type, field_id))

        conn.commit()
        print('[v123 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v123 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv:
        rollback(_db)
    else:
        _ok = migrate(_db)
        print('[v123] migrate: %s' % ('OK' if _ok else 'FAIL'))
        _v = verify(_db)
        print('[v123] verify: %s' % ('PASS' if _v else 'FAIL'))
