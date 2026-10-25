# -*- coding: utf-8 -*-
"""[v130] 销售订单波次 2 W2-F：客户维度匹配键

依据:
  docs/superpowers/specs/2026-10-25-sales-order-wave2-detailed-plan.md
    §8.2 客户维度（v130）
    §8.4 不变量 R-KEY-1 ~ R-KEY-3

范围:
  1. factor_catalogs   增 (sales_order_line, customer_account_id) 因子
  2. key_schemas       增 KS_ITEM_CUST（key_fields=["customer_account_id","item_id"]）
  3. lookup_sequences  增 LK_ITEM_CUST
                       steps=[{1: KS_ITEM_CUST}, {2: KS_ITEM}]
  4. rate_records      在 PL_STD 下增 1 条客户价（示例客户 × 示例物料）
  5. pricing_determinations  PD_STD.lookup_sequence_id 指到 LK_ITEM_CUST
  6. rate_types        复用 RT_LIST_PRICE（不新建）
  7. key_schemas       复用 KS_ITEM（零改动，R-KEY-3）

口径:
  · 因子记在 `sales_order_line` 上：`key_fields` 的元素直接取
    `factor_catalog.field_id`，与 `item_id`（行级）同对象，避免跨对象混用。
  · 客户价与物料价**同处一张价目表**：`lookup` 按槽位先按 `key_schema_id`
    粗筛，客户槽只会看到 `KS_ITEM_CUST` 记录、物料槽只会看到 `KS_ITEM` 记录；
    命中记录的 `hit_policy='exclusive'` 触发命中即停，故客户价优先且不会与
    物料价叠加（`lookup_resolver.lookup` 的 exclusive 语义）。
    分表方案不成立：单条确定规则只定一张价目表，跨表兜底在 `resolve` 层
    没有回退机制，会把"无客户价"直接算成 NO_CANDIDATE。
  · `PD_STD` 只改 `lookup_sequence_id`，价目表 / 定价过程不变；若该列为空或
    已指向别的序列（被人工改过），本迁移不覆盖，只打印提示。

幂等:
  全部按业务键判存在（因子按 object_type + field_id），已存在则 SKIP。
  键表/序列/价目行/规则指向的 SKIP 是**整包复跑不刷新**，不覆盖已配数据。

回滚:
  按依赖倒序删除 rate_records → 还原 PD_STD.lookup_sequence_id →
  lookup_sequences → key_schemas(KS_ITEM_CUST) → factor_catalogs。
"""
import json
import sqlite3
from datetime import date
from pathlib import Path

FACTOR = ('sales_order_line', 'customer_account_id', 'static', 1,
          '客户：经订单抬头继承，用于客户价')

KEY_SCHEMA_CODE = 'KS_ITEM_CUST'
KEY_SCHEMA_NAME = '客户×物料匹配键'
KEY_SCHEMA_FIELDS = ['customer_account_id', 'item_id']

BASE_KEY_SCHEMA_CODE = 'KS_ITEM'

SEQUENCE_CODE = 'LK_ITEM_CUST'
SEQUENCE_NAME = '客户优先查找序列'
BASE_SEQUENCE_CODE = 'LK_ITEM_STD'

RATE_TABLE_CODE = 'PL_STD'
RATE_TYPE_CODE = 'RT_LIST_PRICE'

DETERMINATION_CODE = 'PD_STD'

#: 示例客户价：前端验证客户(4) × 前端验证成品(2)
SAMPLE_CUSTOMER_ID = 4
SAMPLE_ITEM_ID = 2
SAMPLE_RATE = 10.00
RECORD_CODE = 'PT_CUST_4_2'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _one(conn, sql, params):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _code_id(conn, table, code):
    return _one(conn, 'SELECT id FROM %s WHERE code = ?' % table, (code,))


def _factor_exists(conn, object_type, field_id):
    return _one(conn,
                'SELECT id FROM factor_catalogs'
                ' WHERE object_type = ? AND field_id = ?',
                (object_type, field_id)) is not None


def _customer_exists(conn, customer_id):
    return _one(conn, 'SELECT id FROM customer_accounts WHERE id = ?',
                (customer_id,)) is not None


def _item_exists(conn, item_id):
    return _one(conn, 'SELECT id FROM items WHERE id = ?', (item_id,)) is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v130] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v130] 开始: 客户维度匹配键')
        required = ('factor_catalogs', 'key_schemas', 'lookup_sequences',
                    'rate_tables', 'rate_types', 'rate_records', 'items',
                    'customer_accounts', 'pricing_determinations')
        missing = [t for t in required if not _table_exists(conn, t)]
        if missing:
            print('[v130] 缺少表 %s，终止' % missing)
            return False

        base_schema_id = _code_id(conn, 'key_schemas', BASE_KEY_SCHEMA_CODE)
        if not base_schema_id:
            print('[v130] 缺少 %s（波次 1 未点亮），终止' % BASE_KEY_SCHEMA_CODE)
            return False
        rate_table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
        if not rate_table_id:
            print('[v130] 缺少价目表 %s（波次 1 未点亮），终止' % RATE_TABLE_CODE)
            return False

        now = "datetime('now')"

        # 1) 因子
        object_type, field_id, source_type, relevant, desc = FACTOR
        if _factor_exists(conn, object_type, field_id):
            print('  SKIP factor %s/%s' % (object_type, field_id))
        else:
            conn.execute(
                'INSERT INTO factor_catalogs '
                '(object_type, field_id, source_type, is_price_relevant, '
                ' description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, %s, %s)' % (now, now),
                (object_type, field_id, source_type, relevant, desc))
            print('  + INSERT factor %s/%s' % (object_type, field_id))

        # 2) 匹配键表
        if _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE):
            print('  SKIP key_schema %s' % KEY_SCHEMA_CODE)
        else:
            conn.execute(
                'INSERT INTO key_schemas '
                '(code, name, key_fields, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (KEY_SCHEMA_CODE, KEY_SCHEMA_NAME,
                 json.dumps(KEY_SCHEMA_FIELDS),
                 '客户 × 物料：客户价优先，未命中落物料价'))
            print('  + INSERT key_schema %s' % KEY_SCHEMA_CODE)
        cust_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)

        # 3) 查找序列（客户 × 物料 → 物料）
        if _code_id(conn, 'lookup_sequences', SEQUENCE_CODE):
            print('  SKIP lookup_sequence %s' % SEQUENCE_CODE)
        else:
            steps = [
                {'seq': 1, 'key_schema_id': cust_schema_id},
                {'seq': 2, 'key_schema_id': base_schema_id},
            ]
            conn.execute(
                'INSERT INTO lookup_sequences '
                '(code, name, steps, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (SEQUENCE_CODE, SEQUENCE_NAME, json.dumps(steps),
                 '首槽按客户 × 物料查客户价，未命中落物料次槽'))
            print('  + INSERT lookup_sequence %s' % SEQUENCE_CODE)
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)

        # 4) 示例客户价（客户或物料缺失则跳过）
        rate_type_id = _code_id(conn, 'rate_types', RATE_TYPE_CODE)
        if _code_id(conn, 'rate_records', RECORD_CODE):
            print('  SKIP rate_record %s' % RECORD_CODE)
        elif not _customer_exists(conn, SAMPLE_CUSTOMER_ID):
            print('[v130] 缺少客户 %s，跳过客户价种子' % SAMPLE_CUSTOMER_ID)
        elif not _item_exists(conn, SAMPLE_ITEM_ID):
            print('[v130] 缺少物料 %s，跳过客户价种子' % SAMPLE_ITEM_ID)
        elif not rate_type_id:
            print('[v130] 缺少费率类型 %s，跳过客户价种子' % RATE_TYPE_CODE)
        else:
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
                (RECORD_CODE, rate_table_id, cust_schema_id,
                 json.dumps({'customer_account_id': SAMPLE_CUSTOMER_ID,
                             'item_id': SAMPLE_ITEM_ID}),
                 rate_type_id, SAMPLE_RATE, date.today().isoformat(),
                 '客户 %s 对物料 %s 的合同单价'
                 % (SAMPLE_CUSTOMER_ID, SAMPLE_ITEM_ID)))
            print('  + INSERT rate_record %s' % RECORD_CODE)

        # 5) 确定规则改指查找序列（只动这一列，且不覆盖人工改过的指向）
        rule_id = _code_id(conn, 'pricing_determinations', DETERMINATION_CODE)
        if not rule_id:
            print('[v130] 缺少确定规则 %s，跳过改指' % DETERMINATION_CODE)
        else:
            current = _one(conn,
                           'SELECT lookup_sequence_id FROM pricing_determinations'
                           ' WHERE id = ?', (rule_id,))
            if current == sequence_id:
                print('  SKIP determination %s → %s'
                      % (DETERMINATION_CODE, SEQUENCE_CODE))
            elif current == _code_id(conn, 'lookup_sequences', BASE_SEQUENCE_CODE):
                conn.execute(
                    'UPDATE pricing_determinations SET lookup_sequence_id = ?, '
                    'updated_at = %s WHERE id = ?' % now,
                    (sequence_id, rule_id))
                print('  ~ UPDATE determination %s: %s → %s'
                      % (DETERMINATION_CODE, BASE_SEQUENCE_CODE, SEQUENCE_CODE))
            else:
                print('[v130] %s 的查找序列已被改为 %r，不覆盖（跳过改指）'
                      % (DETERMINATION_CODE, current))

        conn.commit()
        print('[v130] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v130] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v130 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _factor_exists(conn, FACTOR[0], FACTOR[1]):
            print('[v130 verify] FAIL: 因子 %s/%s 缺失' % (FACTOR[0], FACTOR[1]))
            return False

        cust_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
        if not cust_schema_id:
            print('[v130 verify] FAIL: 匹配键 %s 缺失' % KEY_SCHEMA_CODE)
            return False
        raw_fields = _one(conn, 'SELECT key_fields FROM key_schemas WHERE id = ?',
                          (cust_schema_id,))
        if json.loads(raw_fields or '[]') != KEY_SCHEMA_FIELDS:
            print('[v130 verify] FAIL: 匹配键字段不符 %s' % (raw_fields,))
            return False

        base_schema_id = _code_id(conn, 'key_schemas', BASE_KEY_SCHEMA_CODE)
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
        if not sequence_id:
            print('[v130 verify] FAIL: 查找序列 %s 缺失' % SEQUENCE_CODE)
            return False
        slots = json.loads(_one(conn,
                                'SELECT steps FROM lookup_sequences WHERE id = ?',
                                (sequence_id,)) or '[]')
        expected = [cust_schema_id, base_schema_id]
        if [s.get('key_schema_id') for s in slots] != expected:
            print('[v130 verify] FAIL: 查找序列槽位不符 %s' % (slots,))
            return False

        rate_table_id = _code_id(conn, 'rate_tables', RATE_TABLE_CODE)
        if not rate_table_id:
            print('[v130 verify] FAIL: 价目表 %s 缺失' % RATE_TABLE_CODE)
            return False

        rule_id = _code_id(conn, 'pricing_determinations', DETERMINATION_CODE)
        if not rule_id:
            print('[v130 verify] FAIL: 确定规则 %s 缺失' % DETERMINATION_CODE)
            return False
        bound = _one(conn, 'SELECT lookup_sequence_id FROM pricing_determinations'
                            ' WHERE id = ?', (rule_id,))
        if bound != sequence_id:
            print('[v130 verify] FAIL: %s 未指向 %s'
                  % (DETERMINATION_CODE, SEQUENCE_CODE))
            return False

        # 客户或物料不存在时种子本就跳过，verify 相应只验配置链
        if (_customer_exists(conn, SAMPLE_CUSTOMER_ID)
                and _item_exists(conn, SAMPLE_ITEM_ID)):
            record = conn.execute(
                'SELECT keys, rate, rate_table_id, key_schema_id, status '
                'FROM rate_records WHERE code = ?', (RECORD_CODE,)).fetchone()
            if not record:
                print('[v130 verify] FAIL: 客户价 %s 缺失' % RECORD_CODE)
                return False
            keys, rate, table_id, schema_id, status = record
            if (json.loads(keys or '{}')
                    != {'customer_account_id': SAMPLE_CUSTOMER_ID,
                        'item_id': SAMPLE_ITEM_ID}
                    or table_id != rate_table_id
                    or schema_id != cust_schema_id
                    or status != 'active'):
                print('[v130 verify] FAIL: 客户价记录不符 %s' % (record,))
                return False
            if float(rate) != SAMPLE_RATE:
                print('[v130 verify] FAIL: 客户价费率不符 %s' % (rate,))
                return False

        print('[v130 verify] OK: 客户因子 + KS_ITEM_CUST + LK_ITEM_CUST(2 槽) '
              '+ PL_STD 客户价 + PD_STD 指到 LK_ITEM_CUST')
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v130 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _code_id(conn, 'rate_records', RECORD_CODE):
            conn.execute('DELETE FROM rate_records WHERE code = ?', (RECORD_CODE,))
            print('  - DELETE rate_record %s' % RECORD_CODE)

        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
        base_sequence_id = _code_id(conn, 'lookup_sequences', BASE_SEQUENCE_CODE)
        rule_id = _code_id(conn, 'pricing_determinations', DETERMINATION_CODE)
        if sequence_id and rule_id and base_sequence_id:
            bound = _one(conn,
                         'SELECT lookup_sequence_id FROM pricing_determinations'
                         ' WHERE id = ?', (rule_id,))
            if bound == sequence_id:
                conn.execute(
                    'UPDATE pricing_determinations SET lookup_sequence_id = ?, '
                    "updated_at = datetime('now') WHERE id = ?",
                    (base_sequence_id, rule_id))
                print('  ~ UPDATE determination %s → %s'
                      % (DETERMINATION_CODE, BASE_SEQUENCE_CODE))

        if sequence_id:
            conn.execute('DELETE FROM lookup_sequences WHERE id = ?',
                         (sequence_id,))
            print('  - DELETE lookup_sequence %s' % SEQUENCE_CODE)

        if _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE):
            conn.execute('DELETE FROM key_schemas WHERE code = ?',
                         (KEY_SCHEMA_CODE,))
            print('  - DELETE key_schema %s' % KEY_SCHEMA_CODE)

        if _factor_exists(conn, FACTOR[0], FACTOR[1]):
            conn.execute('DELETE FROM factor_catalogs '
                         'WHERE object_type = ? AND field_id = ?',
                         (FACTOR[0], FACTOR[1]))
            print('  - DELETE factor %s/%s' % (FACTOR[0], FACTOR[1]))

        conn.commit()
        print('[v130 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v130 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    _args = [a for a in sys.argv[1:] if not a.startswith('-')]
    _db = Path(_args[0]) if _args \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    if '--rollback' in sys.argv:
        rollback(_db)
    else:
        _ok = migrate(_db)
        print('[v130] migrate: %s' % ('OK' if _ok else 'FAIL'))
        _v = verify(_db)
        print('[v130] verify: %s' % ('PASS' if _v else 'FAIL'))
