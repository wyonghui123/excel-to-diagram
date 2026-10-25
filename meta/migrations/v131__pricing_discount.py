# -*- coding: utf-8 -*-
"""[v131] 销售订单波次 2 W2-C：行级折扣与附加费定价链

依据:
  docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md §5

范围:
  1. rate_types      RT_DISC_LINE（sign='-' / percent / manual_allowed）
                     RT_SURCHARGE_LINE（sign='+' / percent）
  2. lookup_sequences LK_ITEM_DISC（单槽位 → KS_ITEM，与标准价同键）
  3. calc_procedures PRICE_STD_DISC
  4. calc_procedure_steps
       seq10 formula  取价（价格类，沿用确定规则给的查找序列）
       seq15 formula  折扣：rolling + running_net_amount * (1 - lookup/100)
       seq18 formula  附加费：rolling + running_net_amount * (1 + lookup/100)
       seq20 round    两位取整
  5. rate_records    示例折扣（物料 1 → 10%、物料 2 → 5%）+ 附加费（物料 2 → 2%）
  6. pricing_determinations PD_STD 的 calc_procedure_id 改指新过程

口径说明（与引擎实现对账）:
  1. 过程里的公式**没有 `result` 变量**（白名单只有 lookup_amount / base /
     running_net_amount / state），故折扣/附加费用 `rolling=true` + 以
     `running_net_amount` 为基数，而不是 `result * (1 - ...)`。
  2. 折扣/附加费的费率类型各自挂查找序列，编排层按步骤费率类型**独立查表**；
     同一价目表内的价格/折扣/附加费记录因此互不串用。
  3. 旧过程 `PRICE_STD` **原样保留**，仅供历史 calc_result 回放。

幂等:
  按 code 判存在（费率类型 / 序列 / 过程 / 价目行），步骤按
  `(calc_procedure_id, seq)` 判存在。`PD_STD` 只在当前仍指向 `PRICE_STD`
  时改指，人工改过则不覆盖。

回滚:
  删价目行 → 还原 PD_STD 指向 PRICE_STD → 删步骤 → 删过程 → 删序列 → 删费率类型。
"""
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

BASE_KEY_SCHEMA_CODE = 'KS_ITEM'
RATE_TABLE_CODE = 'PL_STD'
BASE_PROCEDURE_CODE = 'PRICE_STD'
DETERMINATION_CODE = 'PD_STD'

SEQUENCE_CODE = 'LK_ITEM_DISC'
SEQUENCE_NAME = '物料折扣查找序列'

PRICE_RATE_TYPE_CODE = 'RT_LIST_PRICE'

#: (code, name, sign, numeric_field, description)
RATE_TYPES = (
    ('RT_DISC_LINE', '行级折扣', '-', 'discount_percent',
     '行级折扣百分比：取价目行的费率作为折扣率，允许手工覆盖'),
    ('RT_SURCHARGE_LINE', '行级附加费', '+', 'surcharge_percent',
     '行级附加费百分比：取价目行的费率作为附加费率'),
)

PROCEDURE_CODE = 'PRICE_STD_DISC'
PROCEDURE_NAME = '标准销售定价过程（含行级折扣与附加费）'

#: 步骤模板（rate_type_code 为 None 表示不绑定费率类型）
#: (seq, element_type, rate_type_code, params, rolling, description)
STEPS = (
    (10, 'formula', PRICE_RATE_TYPE_CODE,
     {'expr': 'lookup_amount * base'}, 0,
     '按匹配键取标准单价，并按计算基（行数量）放大为行金额'),
    (15, 'formula', 'RT_DISC_LINE',
     {'expr': 'running_net_amount * (1 - lookup_amount / 100)'}, 1,
     '按命中折扣百分比下浮行净额'),
    (18, 'formula', 'RT_SURCHARGE_LINE',
     {'expr': 'running_net_amount * (1 + lookup_amount / 100)'}, 1,
     '按命中附加费百分比上浮行净额'),
    (20, 'round', None, {'mode': 'round', 'digits': 2}, 0,
     '按两位小数取整，仅用于展示/入账，不参与累加'),
)

#: 必须排在 round 之前的步骤费率类型（R-DSC-3）
_ADJUSTMENT_TYPES = ('RT_DISC_LINE', 'RT_SURCHARGE_LINE')

#: (code, item_id, rate_type_code, rate, description)
RATE_RECORDS = (
    ('PT_DISC_ITEM_1', 1, 'RT_DISC_LINE', 10.0, '物料 1 行级折扣 10%'),
    ('PT_DISC_ITEM_2', 2, 'RT_DISC_LINE', 5.0, '物料 2 行级折扣 5%'),
    ('PT_SUR_ITEM_2', 2, 'RT_SURCHARGE_LINE', 2.0, '物料 2 行级附加费 2%'),
)


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _one(conn, sql, params):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _code_id(conn, table, code):
    return _one(conn, 'SELECT id FROM %s WHERE code = ?' % table, (code,))


def _item_exists(conn, item_id):
    return _one(conn, 'SELECT id FROM items WHERE id = ?', (item_id,)) is not None


def _step_exists(conn, procedure_id, seq):
    return _one(conn, 'SELECT id FROM calc_procedure_steps'
                      ' WHERE calc_procedure_id = ? AND seq = ?',
                (procedure_id, seq)) is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v131] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v131] 开始: 行级折扣与附加费定价链')
        required = ('key_schemas', 'lookup_sequences', 'rate_types',
                    'calc_procedures', 'calc_procedure_steps', 'rate_tables',
                    'rate_records', 'items', 'pricing_determinations')
        missing = [t for t in required if not _table_exists(conn, t)]
        if missing:
            print('[v131] 缺少表 %s，终止' % missing)
            return False

        key_schema_id = _code_id(conn, 'key_schemas', BASE_KEY_SCHEMA_CODE)
        if not key_schema_id:
            print('[v131] 缺少 %s（波次 1 未点亮），终止' % BASE_KEY_SCHEMA_CODE)
            return False
        base_procedure_id = _code_id(conn, 'calc_procedures', BASE_PROCEDURE_CODE)
        if not base_procedure_id:
            print('[v131] 缺少 %s（波次 1 未点亮），终止' % BASE_PROCEDURE_CODE)
            return False
        rate_table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
        if not rate_table_id:
            print('[v131] 缺少 %s（波次 1 未点亮），终止' % RATE_TABLE_CODE)
            return False

        now = "datetime('now')"

        # 1) 查找序列（单槽位，与标准价同键）
        if _code_id(conn, 'lookup_sequences', SEQUENCE_CODE):
            print('  SKIP lookup_sequence %s' % SEQUENCE_CODE)
        else:
            steps = [{'seq': 1, 'key_schema_id': key_schema_id}]
            conn.execute(
                'INSERT INTO lookup_sequences '
                '(code, name, steps, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (SEQUENCE_CODE, SEQUENCE_NAME, json.dumps(steps),
                 '按物料键查折扣/附加费价目行'))
            print('  + INSERT lookup_sequence %s' % SEQUENCE_CODE)
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)

        # 2) 费率类型
        for code, name, sign, numeric_field, desc in RATE_TYPES:
            if _code_id(conn, 'rate_types', code):
                print('  SKIP rate_type %s' % code)
                continue
            conn.execute(
                'INSERT INTO rate_types '
                '(code, name, rate_class, calc_type, rate_source, sign, rounding, '
                ' numeric_field, display_scale, exclusion_group_id, manual_allowed, '
                ' mandatory, statistical, lookup_sequence_id, description, '
                ' created_at, updated_at) '
                "VALUES (?, ?, 'discount_surcharge', 'percent', 'rate_record', ?, "
                " 'round', ?, '2', NULL, 1, 0, 0, ?, ?, %s, %s)" % (now, now),
                (code, name, sign, numeric_field, sequence_id, desc))
            print('  + INSERT rate_type %s' % code)

        # 3) 定价过程
        if _code_id(conn, 'calc_procedures', PROCEDURE_CODE):
            print('  SKIP calc_procedure %s' % PROCEDURE_CODE)
        else:
            conn.execute(
                'INSERT INTO calc_procedures '
                '(code, name, procedure_type, result_semantic, currency, '
                ' subtotal_keys, description, created_at, updated_at) '
                "VALUES (?, ?, 'pricing', 'price', NULL, '[]', ?, %s, %s)"
                % (now, now),
                (PROCEDURE_CODE, PROCEDURE_NAME,
                 '标准销售定价过程：查表得单价 → 行级折扣 → 行级附加费 → 取整'))
            print('  + INSERT calc_procedure %s' % PROCEDURE_CODE)
        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)

        # 4) 计算步骤
        for seq, element_type, rate_type_code, params, rolling, desc in STEPS:
            if _step_exists(conn, procedure_id, seq):
                print('  SKIP calc_procedure_step %s/%s' % (PROCEDURE_CODE, seq))
                continue
            step_rate_type_id = (_code_id(conn, 'rate_types', rate_type_code)
                                 if rate_type_code else None)
            conn.execute(
                'INSERT INTO calc_procedure_steps '
                '(calc_procedure_id, seq, element_type, rate_type_id, condition, '
                ' params, rolling, base_step, subtotal_key, description, '
                ' created_at, updated_at) '
                'VALUES (?, ?, ?, ?, NULL, ?, ?, NULL, NULL, ?, %s, %s)'
                % (now, now),
                (procedure_id, seq, element_type, step_rate_type_id,
                 json.dumps(params), rolling, desc))
            print('  + INSERT calc_procedure_step %s/%s' % (PROCEDURE_CODE, seq))

        # 5) 示例价目行（缺物料则跳过）
        today = date.today().isoformat()
        for code, item_id, rate_type_code, rate, desc in RATE_RECORDS:
            if _code_id(conn, 'rate_records', code):
                print('  SKIP rate_record %s' % code)
                continue
            if not _item_exists(conn, item_id):
                print('[v131] 缺少物料 %s，跳过价目行 %s' % (item_id, code))
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
                 json.dumps({'item_id': item_id}),
                 _code_id(conn, 'rate_types', rate_type_code), rate,
                 today, desc))
            print('  + INSERT rate_record %s' % code)

        # 6) 确定规则改指新过程（只在当前仍指向旧过程时改写）
        current_id = _one(conn, 'SELECT calc_procedure_id FROM pricing_determinations'
                                ' WHERE code = ?', (DETERMINATION_CODE,))
        if current_id is None:
            print('[v131] 缺少确定规则 %s，跳过改指' % DETERMINATION_CODE)
        elif current_id == procedure_id:
            print('  SKIP pricing_determination %s（已指向 %s）'
                  % (DETERMINATION_CODE, PROCEDURE_CODE))
        elif current_id == base_procedure_id:
            conn.execute(
                'UPDATE pricing_determinations SET calc_procedure_id = ?'
                ' WHERE code = ?', (procedure_id, DETERMINATION_CODE))
            print('  ~ UPDATE pricing_determination %s → %s'
                  % (DETERMINATION_CODE, PROCEDURE_CODE))
        else:
            print('  SKIP pricing_determination %s（已指向其他过程，不覆盖）'
                  % DETERMINATION_CODE)

        conn.commit()
        print('[v131] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v131] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v131 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        key_schema_id = _code_id(conn, 'key_schemas', BASE_KEY_SCHEMA_CODE)
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
        if not sequence_id:
            print('[v131 verify] FAIL: 查找序列 %s 缺失' % SEQUENCE_CODE)
            return False
        raw_steps = _one(conn, 'SELECT steps FROM lookup_sequences WHERE id = ?',
                         (sequence_id,))
        try:
            slots = json.loads(raw_steps or '[]')
        except (TypeError, ValueError):
            slots = []
        if not slots or slots[0].get('key_schema_id') != key_schema_id:
            print('[v131 verify] FAIL: 查找序列槽位未指向 %s' % BASE_KEY_SCHEMA_CODE)
            return False

        for code, name, sign, numeric_field, _desc in RATE_TYPES:
            row = conn.execute(
                'SELECT rate_class, calc_type, sign, numeric_field, '
                '       lookup_sequence_id, manual_allowed '
                '  FROM rate_types WHERE code = ?', (code,)).fetchone()
            expected = ('discount_surcharge', 'percent', sign, numeric_field,
                        sequence_id, 1)
            if row != expected:
                print('[v131 verify] FAIL: 费率类型 %s 不符 %s' % (code, row))
                return False

        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
        if not procedure_id:
            print('[v131 verify] FAIL: 定价过程 %s 缺失' % PROCEDURE_CODE)
            return False
        rows = conn.execute(
            'SELECT seq, element_type, rate_type_id, rolling FROM '
            'calc_procedure_steps WHERE calc_procedure_id = ? ORDER BY seq',
            (procedure_id,)).fetchall()
        if [(r[0], r[1], bool(r[3])) for r in rows] != [
                (seq, et, bool(rolling)) for seq, et, _rt, _p, rolling, _d in STEPS]:
            print('[v131 verify] FAIL: 过程步骤不符 %s' % (rows,))
            return False

        # R-DSC-3：折扣/附加费步骤必须早于 round
        seq_by_rate_type = {}
        for seq, _et, rt_id, _rolling in rows:
            rt_code = _one(conn, 'SELECT code FROM rate_types WHERE id = ?', (rt_id,))
            seq_by_rate_type[rt_code] = seq
        round_seq = next((r[0] for r in rows if r[1] == 'round'), None)
        for code in _ADJUSTMENT_TYPES:
            seq = seq_by_rate_type.get(code)
            if seq is None:
                print('[v131 verify] FAIL: 缺少 %s 步骤' % code)
                return False
            if round_seq is not None and seq > round_seq:
                print('[v131 verify] FAIL: %s 步骤须早于 round（%s > %s）'
                      % (code, seq, round_seq))
                return False

        for code, item_id, _rt, _rate, _desc in RATE_RECORDS:
            if not _item_exists(conn, item_id):
                continue
            row = conn.execute(
                'SELECT rate_table_id, keys, status FROM rate_records WHERE code = ?',
                (code,)).fetchone()
            if not row:
                print('[v131 verify] FAIL: 价目行 %s 缺失' % code)
                return False
            if row[0] != _code_id(conn, 'rate_tables', RATE_TABLE_CODE):
                print('[v131 verify] FAIL: 价目行 %s 未落在 %s'
                      % (code, RATE_TABLE_CODE))
                return False
            if row[2] != 'active':
                print('[v131 verify] FAIL: 价目行 %s 非 active' % code)
                return False
            if json.loads(row[1] or '{}').get('item_id') != item_id:
                print('[v131 verify] FAIL: 价目行 %s 键值不符' % code)
                return False

        rule_proc = _one(conn, 'SELECT calc_procedure_id FROM '
                               'pricing_determinations WHERE code = ?',
                         (DETERMINATION_CODE,))
        if rule_proc != procedure_id:
            print('[v131 verify] FAIL: %s 未指向 %s'
                  % (DETERMINATION_CODE, PROCEDURE_CODE))
            return False

        print('[v131 verify] OK: RT_DISC_LINE + RT_SURCHARGE_LINE + LK_ITEM_DISC '
              '+ PRICE_STD_DISC(4 步) + 折扣/附加费价目行 + PD_STD 改指')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v131 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for code, _item_id, _rt, _rate, _desc in RATE_RECORDS:
            if _code_id(conn, 'rate_records', code):
                conn.execute('DELETE FROM rate_records WHERE code = ?', (code,))
                print('  - DELETE rate_record %s' % code)

        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
        base_procedure_id = _code_id(conn, 'calc_procedures', BASE_PROCEDURE_CODE)
        current_id = _one(conn, 'SELECT calc_procedure_id FROM pricing_determinations'
                                ' WHERE code = ?', (DETERMINATION_CODE,))
        if procedure_id and current_id == procedure_id and base_procedure_id:
            conn.execute(
                'UPDATE pricing_determinations SET calc_procedure_id = ?'
                ' WHERE code = ?', (base_procedure_id, DETERMINATION_CODE))
            print('  ~ RESTORE pricing_determination %s → %s'
                  % (DETERMINATION_CODE, BASE_PROCEDURE_CODE))

        if procedure_id:
            conn.execute('DELETE FROM calc_procedure_steps WHERE calc_procedure_id = ?',
                         (procedure_id,))
            conn.execute('DELETE FROM calc_procedures WHERE id = ?', (procedure_id,))
            print('  - DELETE calc_procedure %s' % PROCEDURE_CODE)

        if _code_id(conn, 'lookup_sequences', SEQUENCE_CODE):
            conn.execute('DELETE FROM lookup_sequences WHERE code = ?',
                         (SEQUENCE_CODE,))
            print('  - DELETE lookup_sequence %s' % SEQUENCE_CODE)

        for code, _name, _sign, _field, _desc in RATE_TYPES:
            if _code_id(conn, 'rate_types', code):
                conn.execute('DELETE FROM rate_types WHERE code = ?', (code,))
                print('  - DELETE rate_type %s' % code)

        conn.commit()
        print('[v131 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v131 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    _args = [a for a in sys.argv[1:] if not a.startswith('-')]
    _db = Path(_args[0]) if _args \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv:
        rollback(_db)
    else:
        _ok = migrate(_db)
        print('[v131] migrate: %s' % ('OK' if _ok else 'FAIL'))
        _v = verify(_db)
        print('[v131] verify: %s' % ('PASS' if _v else 'FAIL'))
