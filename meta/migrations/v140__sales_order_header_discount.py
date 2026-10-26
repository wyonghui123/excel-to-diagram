# -*- coding: utf-8 -*-
"""[v140] 销售订单抬头折扣 + 按行分摊：定价与分摊种子

依据:
  docs/superpowers/specs/2026-10-26-sales-order-billing-and-header-discount-spec.md
    §4.2 种子对象（rate_type / lookup_sequence / calc_procedure / allocation_rule）
    §4.3 抬头结果落 calc_results（document_type='sales_order'、level='header'）
    §4.7 分摊留痕复用 allocation_results（basis='value' / rounding='round'）

范围（只 upsert 数据，不建表）:
  1. key_schemas         KS_CUST_CURRENCY（key_fields=["customer_account_id","currency"]）
  2. lookup_sequences    LK_DISC_HEADER（单槽位 → KS_CUST_CURRENCY）
  3. rate_types          RT_DISC_HEADER / RT_SURCHARGE_HEADER（discount_surcharge / 百分比）
  4. calc_procedures     PRICE_STD_HDR_DISC（抬头定价过程）
  5. calc_procedure_steps
       seq10 formula  抬头基价（base_source=value / base_level=header，基值由调用方传入）
       seq15 formula  折扣：rolling + running_net_amount * (1 - lookup_amount / 100)
       seq18 formula  附加费：rolling + running_net_amount * (1 + lookup_amount / 100)
       seq20 round    ROUND_HALF_UP 两位（执行器 mode='round' 即 Decimal 半进位）
  6. allocation_rules    AR_HDR_DISC_BY_NET（basis='value' / rounding='round'）

与 Spec §4.2 的落库偏差（以真实表结构为准）:
  1. 槽位没有独立表：lookup_sequences.steps 是 JSON 数组，元素只带
     {seq, key_schema_id}；故「customer_account_id + currency」必须表达为
     一把复合匹配键 KS_CUST_CURRENCY，再挂到 LK_DISC_HEADER 的槽位 1。
  2. base_source / base_level 不是 calc_procedure_steps 的列（它们属于
     calc_detail / calc_result 的结果字段），故写进 seq10 的 params JSON 留痕，
     实际基值由调用方通过 execute(base=Σ net_line) 传入。
  3. allocation_rules 真实列没有 status / is_active / document_type，且
     target 是 NOT NULL DEFAULT 'cost'（枚举只有 cost / expense），
     Spec 的「status=active」「target 留空」无法落列，故 target 取默认 'cost'。

幂等:
  全部按业务 code 判存在；已存在输出 [SKIP]，不刷新既配。步骤按
  (calc_procedure_id, seq) 判存在。整包复跑第二次应全部 [SKIP]。

回滚:
  按依赖倒序删除 allocation_rule → 步骤 → 过程 → 费率类型 → 查找序列 →
  匹配键。已被运行期数据引用的对象保留并输出 [KEEP]，只删本迁移插入的对象。
"""
import json
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

KEY_SCHEMA_CODE = 'KS_CUST_CURRENCY'
KEY_SCHEMA_NAME = '客户+币种匹配键'
KEY_SCHEMA_FIELDS = ['customer_account_id', 'currency']

SEQUENCE_CODE = 'LK_DISC_HEADER'
SEQUENCE_NAME = '抬头折扣/附加费查找序列'

PROCEDURE_CODE = 'PRICE_STD_HDR_DISC'
PROCEDURE_NAME = '抬头定价过程（抬头折扣与附加费）'

ALLOCATION_RULE_CODE = 'AR_HDR_DISC_BY_NET'
ALLOCATION_RULE_NAME = '抬头折扣/附加费按行净额分摊'

#: (code, name, sign, numeric_field, description)
RATE_TYPES = (
    ('RT_DISC_HEADER', '抬头折扣', '-', 'discount_percent',
     '抬头折扣百分比：按客户+币种取费率，允许手工覆盖'),
    ('RT_SURCHARGE_HEADER', '抬头附加费', '+', 'surcharge_percent',
     '抬头附加费百分比：按客户+币种取费率，允许手工覆盖'),
)

#: (seq, element_type, rate_type_code, params, rolling, description)
STEPS = (
    (10, 'formula', None,
     {'expr': 'base', 'base_source': 'value', 'base_level': 'header'}, 1,
     '抬头基价：基值由调用方传入（Σ 行净额），本步只把基值落为滚动净额起点'),
    (15, 'formula', 'RT_DISC_HEADER',
     {'expr': 'running_net_amount * (1 - lookup_amount / 100)'}, 1,
     '按命中抬头折扣百分比整单下浮'),
    (18, 'formula', 'RT_SURCHARGE_HEADER',
     {'expr': 'running_net_amount * (1 + lookup_amount / 100)'}, 1,
     '按命中抬头附加费百分比整单上浮'),
    (20, 'round', None,
     {'mode': 'round', 'digits': 2, 'rounding': 'ROUND_HALF_UP'}, 0,
     '按 ROUND_HALF_UP 取整到两位（展示/入账，不参与累加）'),
)

#: 本迁移插入的步骤 seq（回滚时只删这些）
STEP_SEQS = tuple(step[0] for step in STEPS)

#: 抬头折扣/附加费步骤必须在 round 之前（R-DSC-3 同口径）
_ADJUSTMENT_TYPES = ('RT_DISC_HEADER', 'RT_SURCHARGE_HEADER')


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _one(conn, sql, params):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def _count(conn, table, code):
    return _one(conn, 'SELECT COUNT(*) FROM %s WHERE code = ?' % table, (code,))


def _code_id(conn, table, code):
    return _one(conn, 'SELECT id FROM %s WHERE code = ?' % table, (code,))


def _step_exists(conn, procedure_id, seq):
    return _one(conn, 'SELECT id FROM calc_procedure_steps'
                      ' WHERE calc_procedure_id = ? AND seq = ?',
                (procedure_id, seq)) is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v140] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v140] 开始: 抬头折扣 + 按行分摊种子')
        required = ('key_schemas', 'lookup_sequences', 'rate_types',
                    'calc_procedures', 'calc_procedure_steps', 'allocation_rules')
        missing = [t for t in required if not _table_exists(conn, t)]
        if missing:
            print('[v140] 缺少表 %s，终止（请先跑 sync_schema 建表）' % missing)
            return False

        now = "datetime('now')"

        # 1) 复合匹配键（客户 + 币种）
        if _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE):
            print('  - [SKIP] key_schema %s' % KEY_SCHEMA_CODE)
        else:
            conn.execute(
                'INSERT INTO key_schemas '
                '(code, name, key_fields, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (KEY_SCHEMA_CODE, KEY_SCHEMA_NAME,
                 json.dumps(KEY_SCHEMA_FIELDS),
                 '按客户账号 + 币种匹配抬头折扣/附加费'))
            print('  - [NEW] key_schema %s' % KEY_SCHEMA_CODE)
        key_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)

        # 2) 查找序列（单槽位 → 复合键）
        if _code_id(conn, 'lookup_sequences', SEQUENCE_CODE):
            print('  - [SKIP] lookup_sequence %s' % SEQUENCE_CODE)
        else:
            steps = [{'seq': 1, 'key_schema_id': key_schema_id}]
            conn.execute(
                'INSERT INTO lookup_sequences '
                '(code, name, steps, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (SEQUENCE_CODE, SEQUENCE_NAME, json.dumps(steps),
                 '槽位 1：按客户账号 + 币种查抬头折扣/附加费'))
            print('  - [NEW] lookup_sequence %s' % SEQUENCE_CODE)
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)

        # 3) 费率类型
        for code, name, sign, numeric_field, desc in RATE_TYPES:
            if _code_id(conn, 'rate_types', code):
                print('  - [SKIP] rate_type %s' % code)
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
            print('  - [NEW] rate_type %s' % code)

        # 4) 抬头定价过程
        if _code_id(conn, 'calc_procedures', PROCEDURE_CODE):
            print('  - [SKIP] calc_procedure %s' % PROCEDURE_CODE)
        else:
            conn.execute(
                'INSERT INTO calc_procedures '
                '(code, name, procedure_type, result_semantic, currency, '
                ' subtotal_keys, description, created_at, updated_at) '
                "VALUES (?, ?, 'pricing', 'price', NULL, '[]', ?, %s, %s)"
                % (now, now),
                (PROCEDURE_CODE, PROCEDURE_NAME,
                 '抬头定价过程：基价（Σ 行净额）→ 抬头折扣 → 抬头附加费 → 取整'))
            print('  - [NEW] calc_procedure %s' % PROCEDURE_CODE)
        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)

        # 5) 计算步骤
        for seq, element_type, rate_type_code, params, rolling, desc in STEPS:
            if _step_exists(conn, procedure_id, seq):
                print('  - [SKIP] calc_procedure_step %s/%s'
                      % (PROCEDURE_CODE, seq))
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
            print('  - [NEW] calc_procedure_step %s/%s'
                  % (PROCEDURE_CODE, seq))

        # 6) 分摊规则
        if _code_id(conn, 'allocation_rules', ALLOCATION_RULE_CODE):
            print('  - [SKIP] allocation_rule %s' % ALLOCATION_RULE_CODE)
        else:
            conn.execute(
                'INSERT INTO allocation_rules '
                '(code, name, basis, manual_factor, group_by, rounding, floor, '
                ' target, description, created_at, updated_at) '
                "VALUES (?, ?, 'value', NULL, NULL, 'round', NULL, 'cost', ?, "
                " %s, %s)" % (now, now),
                (ALLOCATION_RULE_CODE, ALLOCATION_RULE_NAME,
                 '把抬头折扣/附加费按各行净额（net_amount）占比分摊回行；'
                 'target 取真实列默认 cost（schema 中不可为空）'))
            print('  - [NEW] allocation_rule %s' % ALLOCATION_RULE_CODE)

        conn.commit()
        print('[v140] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v140] migrate 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 5 类种子对象各 1 行（费率类型 2 行）+ 步骤恰好 4 步。"""
    if not db_path.exists():
        print('[v140 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        # 1) 匹配键（槽位目标）
        key_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
        if not key_schema_id:
            print('[v140 verify] FAIL: 匹配键 %s 缺失' % KEY_SCHEMA_CODE)
            return False
        raw_fields = _one(conn, 'SELECT key_fields FROM key_schemas WHERE id = ?',
                          (key_schema_id,))
        if json.loads(raw_fields or '[]') != KEY_SCHEMA_FIELDS:
            print('[v140 verify] FAIL: %s.key_fields 不符 %s'
                  % (KEY_SCHEMA_CODE, raw_fields))
            return False

        # 2) 查找序列 + 槽位
        if _count(conn, 'lookup_sequences', SEQUENCE_CODE) != 1:
            print('[v140 verify] FAIL: 查找序列 %s 行数不为 1' % SEQUENCE_CODE)
            return False
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
        raw_steps = _one(conn, 'SELECT steps FROM lookup_sequences WHERE id = ?',
                         (sequence_id,))
        try:
            slots = json.loads(raw_steps or '[]')
        except (TypeError, ValueError):
            slots = []
        if len(slots) != 1 or slots[0].get('key_schema_id') != key_schema_id:
            print('[v140 verify] FAIL: 查找序列槽位未指向 %s' % KEY_SCHEMA_CODE)
            return False

        # 3) 费率类型各 1 行
        for code, _name, sign, numeric_field, _desc in RATE_TYPES:
            if _count(conn, 'rate_types', code) != 1:
                print('[v140 verify] FAIL: 费率类型 %s 行数不为 1' % code)
                return False
            row = conn.execute(
                'SELECT rate_class, calc_type, sign, numeric_field, '
                '       lookup_sequence_id, manual_allowed '
                '  FROM rate_types WHERE code = ?', (code,)).fetchone()
            expected = ('discount_surcharge', 'percent', sign, numeric_field,
                        sequence_id, 1)
            if row != expected:
                print('[v140 verify] FAIL: 费率类型 %s 不符 %s' % (code, row))
                return False

        # 4) 定价过程 1 行
        if _count(conn, 'calc_procedures', PROCEDURE_CODE) != 1:
            print('[v140 verify] FAIL: 定价过程 %s 行数不为 1' % PROCEDURE_CODE)
            return False
        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)

        # 5) 步骤恰好 4 步（10/15/18/20）
        rows = conn.execute(
            'SELECT seq, element_type, rate_type_id, params, rolling FROM '
            'calc_procedure_steps WHERE calc_procedure_id = ? ORDER BY seq',
            (procedure_id,)).fetchall()
        if len(rows) != len(STEPS):
            print('[v140 verify] FAIL: %s 步骤数 %s != %s'
                  % (PROCEDURE_CODE, len(rows), len(STEPS)))
            return False
        if [r[0] for r in rows] != list(STEP_SEQS):
            print('[v140 verify] FAIL: 步骤 seq 不符 %s' % ([r[0] for r in rows],))
            return False

        seq_by_rate_type = {}
        for seq, element_type, rate_type_id, raw_params, rolling in rows:
            rate_type_code = (_one(conn, 'SELECT code FROM rate_types WHERE id = ?',
                                   (rate_type_id,))
                              if rate_type_id else None)
            seq_by_rate_type[rate_type_code] = seq
            params = json.loads(raw_params or '{}')
            # seq10 基价口径
            if seq == 10:
                if (params.get('base_source') != 'value'
                        or params.get('base_level') != 'header'):
                    print('[v140 verify] FAIL: seq10 基价口径不符 %s' % params)
                    return False
            # seq20 取整口径
            if seq == 20:
                if (element_type != 'round' or params.get('mode') != 'round'
                        or int(params.get('digits', 0)) != 2
                        or params.get('rounding') != 'ROUND_HALF_UP'):
                    print('[v140 verify] FAIL: seq20 取整口径不符 %s' % params)
                    return False
            # 折扣/附加费步骤必须 rolling
            if rate_type_code in _ADJUSTMENT_TYPES and not bool(rolling):
                print('[v140 verify] FAIL: %s 步骤未开启 rolling' % rate_type_code)
                return False

        if seq_by_rate_type.get('RT_DISC_HEADER') != 15:
            print('[v140 verify] FAIL: 抬头折扣步骤 seq 应为 15')
            return False
        if seq_by_rate_type.get('RT_SURCHARGE_HEADER') != 18:
            print('[v140 verify] FAIL: 抬头附加费步骤 seq 应为 18')
            return False

        # 6) 分摊规则 1 行
        if _count(conn, 'allocation_rules', ALLOCATION_RULE_CODE) != 1:
            print('[v140 verify] FAIL: 分摊规则 %s 行数不为 1'
                  % ALLOCATION_RULE_CODE)
            return False
        row = conn.execute(
            'SELECT basis, rounding FROM allocation_rules WHERE code = ?',
            (ALLOCATION_RULE_CODE,)).fetchone()
        if row != ('value', 'round'):
            print('[v140 verify] FAIL: 分摊规则 %s 口径不符 %s'
                  % (ALLOCATION_RULE_CODE, row))
            return False

        print('[v140 verify] OK: %s + %s + %s/%s + %s(%s 步) + %s'
              % (KEY_SCHEMA_CODE, SEQUENCE_CODE,
                 RATE_TYPES[0][0], RATE_TYPES[1][0],
                 PROCEDURE_CODE, len(STEPS), ALLOCATION_RULE_CODE))
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """按依赖倒序删除本迁移插入的对象；运行期已引用的保留 [KEEP]。"""
    if not db_path.exists():
        print('[v140 rollback] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v140] 回滚: 抬头折扣 + 按行分摊种子')

        # 1) 分摊规则
        rule_id = _code_id(conn, 'allocation_rules', ALLOCATION_RULE_CODE)
        if not rule_id:
            print('  - [SKIP] allocation_rule %s 不存在' % ALLOCATION_RULE_CODE)
        elif (_table_exists(conn, 'allocation_results')
              and _one(conn, 'SELECT id FROM allocation_results'
                             ' WHERE allocation_rule_id = ? LIMIT 1', (rule_id,))):
            print('  - [KEEP] allocation_rule %s（已被分摊结果引用）'
                  % ALLOCATION_RULE_CODE)
        else:
            conn.execute('DELETE FROM allocation_rules WHERE id = ?', (rule_id,))
            print('  - [DROP] allocation_rule %s' % ALLOCATION_RULE_CODE)

        # 2) 步骤 → 过程
        procedure_id = _code_id(conn, 'calc_procedures', PROCEDURE_CODE)
        if not procedure_id:
            print('  - [SKIP] calc_procedure %s 不存在' % PROCEDURE_CODE)
        else:
            removed = 0
            for seq in STEP_SEQS:
                cur = conn.execute(
                    'DELETE FROM calc_procedure_steps'
                    ' WHERE calc_procedure_id = ? AND seq = ?',
                    (procedure_id, seq))
                removed += cur.rowcount
            print('  - [DROP] calc_procedure_step %s x%s'
                  % (PROCEDURE_CODE, removed))
            remaining = _one(conn, 'SELECT COUNT(*) FROM calc_procedure_steps'
                                    ' WHERE calc_procedure_id = ?', (procedure_id,))
            if remaining:
                print('  - [KEEP] calc_procedure %s（仍有 %s 个非本迁移步骤）'
                      % (PROCEDURE_CODE, remaining))
            else:
                conn.execute('DELETE FROM calc_procedures WHERE id = ?',
                             (procedure_id,))
                print('  - [DROP] calc_procedure %s' % PROCEDURE_CODE)

        # 3) 费率类型
        for code, _name, _sign, _field, _desc in RATE_TYPES:
            rate_type_id = _code_id(conn, 'rate_types', code)
            if not rate_type_id:
                print('  - [SKIP] rate_type %s 不存在' % code)
            elif (_table_exists(conn, 'rate_records')
                  and _one(conn, 'SELECT id FROM rate_records'
                                 ' WHERE rate_type_id = ? LIMIT 1', (rate_type_id,))):
                print('  - [KEEP] rate_type %s（仍被价目行引用）' % code)
            else:
                conn.execute('DELETE FROM rate_types WHERE id = ?', (rate_type_id,))
                print('  - [DROP] rate_type %s' % code)

        # 4) 查找序列
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_CODE)
        if not sequence_id:
            print('  - [SKIP] lookup_sequence %s 不存在' % SEQUENCE_CODE)
        elif _one(conn, 'SELECT id FROM rate_types'
                        ' WHERE lookup_sequence_id = ? LIMIT 1', (sequence_id,)):
            print('  - [KEEP] lookup_sequence %s（仍被费率类型引用）'
                  % SEQUENCE_CODE)
        else:
            conn.execute('DELETE FROM lookup_sequences WHERE id = ?',
                         (sequence_id,))
            print('  - [DROP] lookup_sequence %s' % SEQUENCE_CODE)

        # 5) 匹配键
        key_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_CODE)
        if not key_schema_id:
            print('  - [SKIP] key_schema %s 不存在' % KEY_SCHEMA_CODE)
        elif (_table_exists(conn, 'rate_records')
              and _one(conn, 'SELECT id FROM rate_records'
                             ' WHERE key_schema_id = ? LIMIT 1', (key_schema_id,))):
            print('  - [KEEP] key_schema %s（仍被价目行引用）' % KEY_SCHEMA_CODE)
        else:
            conn.execute('DELETE FROM key_schemas WHERE id = ?', (key_schema_id,))
            print('  - [DROP] key_schema %s' % KEY_SCHEMA_CODE)

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[v140] rollback 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print('[v140] rollback: %s' % ('OK' if _ok else 'FAIL'))
    else:
        _ok = migrate(_db)
        print('[v140] migrate: %s' % ('OK' if _ok else 'FAIL'))
        _v = verify(_db)
        print('[v140] verify: %s' % ('PASS' if _v else 'FAIL'))
