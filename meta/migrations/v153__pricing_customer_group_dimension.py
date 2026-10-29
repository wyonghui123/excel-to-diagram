# -*- coding: utf-8 -*-
"""[v153] 客户组（customer_group_id）进入定价匹配键（T2.3 / B4）

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/b4_attribute_condition_design.md

结论（设计口径）:
  属性条件不引入独立 `conditions` json 列，而是复用既有「键表 + 因子目录」载体：
  一个属性条件 = 一个 `key_schemas.key_fields` 因子组合。
  首批只落 `customer_group_id`；物料组 / 客户地区等同类维度是后续扩展点，
  按同一模式追加 factor + key_schema + 序列槽位即可，不需改本迁移。

范围（同一迁移内完成，幂等）:
  1. factor_catalogs   增 (sales_order_line, customer_group_id) 因子
  2. key_schemas       增 KS_GROUP_ITEM（["customer_group_id","item_id"]）
  3. lookup_sequences  LK_ITEM_CUST：在 org 首槽之后、customer 槽之前插入
                       group 槽，并整体重排 seq（1..n）
  4. 服务注入（不在本迁移内）: _slot_keys 以因子名 customer_group_id 注入组值

边界:
  · 不迁移 / 不回填 rate_records，不 seed 任何业务价目数据。
  · 客户组只决定候选命中；折扣 / 附加费仍按 `rate_type` 独立查表（W2-C）；
    数量段归阶梯（FR-009）；抬头折扣与附加费互斥沿用 v140 口径。

幂等:
  · 因子按 (object_type, field_id) 判存在；键表按 code 判存在；
  · 序列已含 group 槽则 SKIP；否则插入并整体重排（重复执行终态一致）。

回滚:
  序列去掉 group 槽并重排 → 删除 KS_GROUP_ITEM（仍被引用则保留）→ 删除因子。
"""
import json
import sqlite3
import sys
from pathlib import Path

#: (object_type, field_id, source_type, is_price_relevant, description)
GROUP_FACTOR = ('sales_order_line', 'customer_group_id', 'static', 1,
                '客户组：定价匹配键的客户分组维度（组价按 party_relations.group_id 区分）')

KEY_SCHEMA_GROUP_ITEM = 'KS_GROUP_ITEM'
KEY_SCHEMA_GROUP_ITEM_FIELDS = ['customer_group_id', 'item_id']
KEY_SCHEMA_GROUP_ITEM_NAME = '客户组×物料匹配键'

#: 目标查找序列（v130 客户优先序列）
SEQUENCE_TARGET = 'LK_ITEM_CUST'

#: 「客户 × 物料」键表字段集合（group 槽插在它之前）
CUSTOMER_ITEM_FIELDS = frozenset(['customer_account_id', 'item_id'])

REQUIRED_TABLES = ('factor_catalogs', 'key_schemas', 'lookup_sequences')


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


def _schema_fields(conn, schema_id):
    """返回键表 key_fields（list）；schema 不存在或 json 畸形返回 []。"""
    raw = _one(conn, 'SELECT key_fields FROM key_schemas WHERE id = ?',
               (schema_id,))
    try:
        fields = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return []
    return fields if isinstance(fields, list) else []


def _load_steps(conn, sequence_id):
    raw = _one(conn, 'SELECT steps FROM lookup_sequences WHERE id = ?',
               (sequence_id,))
    try:
        steps = json.loads(raw or '[]')
    except (TypeError, ValueError):
        return []
    return steps if isinstance(steps, list) else []


def _insert_group_slot(conn, sequence_code, group_schema_id):
    """把 group 键表插到 customer 槽之前；已存在则跳过。返回是否发生改动。"""
    sequence_id = _code_id(conn, 'lookup_sequences', sequence_code)
    if not sequence_id:
        print('  - [SKIP] 查找序列 %s 不存在（波次 2 未点亮？）' % sequence_code)
        return False
    steps = _load_steps(conn, sequence_id)
    if not steps:
        print('  - [SKIP] 查找序列 %s 槽位为空' % sequence_code)
        return False
    if any((s or {}).get('key_schema_id') == group_schema_id for s in steps):
        print('  - [SKIP] 查找序列 %s 已含 group 槽' % sequence_code)
        return False

    ordered = sorted(steps, key=lambda s: (s or {}).get('seq') or 0)

    # 目标位置 = 「客户 × 物料」槽之前（org 槽在其前，自然保留在最前）
    insert_at = None
    for index, step in enumerate(ordered):
        fields = _schema_fields(conn, (step or {}).get('key_schema_id'))
        if frozenset(fields) == CUSTOMER_ITEM_FIELDS:
            insert_at = index
            break
    if insert_at is None:
        insert_at = len(ordered)
        print('  - [WARN] 查找序列 %s 未找到客户×物料槽，group 槽追加到末尾'
              % sequence_code)

    merged = [dict(step or {}) for step in ordered]
    merged.insert(insert_at, {'key_schema_id': group_schema_id})
    new_steps = []
    for index, step in enumerate(merged, start=1):
        step = dict(step)
        step['seq'] = index
        new_steps.append(step)

    conn.execute(
        "UPDATE lookup_sequences SET steps = ?, updated_at = datetime('now')"
        ' WHERE id = ?',
        (json.dumps(new_steps), sequence_id))
    print('  - [SEQ] %s 第 %d 槽 → %s（共 %d 槽）'
          % (sequence_code, insert_at + 1, group_schema_id, len(new_steps)))
    return True


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v153] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v153] 开始: 客户组进入定价匹配键')
        missing = [t for t in REQUIRED_TABLES if not _table_exists(conn, t)]
        if missing:
            print('  - [FAIL] 缺表 %s' % missing)
            return False

        now = "datetime('now')"

        # 1) 因子
        object_type, field_id, source_type, relevant, desc = GROUP_FACTOR
        if _factor_exists(conn, object_type, field_id):
            print('  - [SKIP] 因子 %s/%s 已存在' % (object_type, field_id))
        else:
            conn.execute(
                'INSERT INTO factor_catalogs '
                '(object_type, field_id, source_type, is_price_relevant, '
                ' description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, %s, %s)' % (now, now),
                (object_type, field_id, source_type, relevant, desc))
            print('  - [FACTOR] + %s/%s' % (object_type, field_id))

        # 2) group 键表
        if _code_id(conn, 'key_schemas', KEY_SCHEMA_GROUP_ITEM):
            print('  - [SKIP] 键表 %s 已存在' % KEY_SCHEMA_GROUP_ITEM)
        else:
            conn.execute(
                'INSERT INTO key_schemas '
                '(code, name, key_fields, description, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                (KEY_SCHEMA_GROUP_ITEM, KEY_SCHEMA_GROUP_ITEM_NAME,
                 json.dumps(KEY_SCHEMA_GROUP_ITEM_FIELDS),
                 '客户组 × 物料：组价优先于客户价，未命中落客户/物料价'))
            print('  - [KS] + %s' % KEY_SCHEMA_GROUP_ITEM)

        group_schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_GROUP_ITEM)
        if not group_schema_id:
            print('  - [FAIL] 键表 %s 缺失，跳过序列 %s'
                  % (KEY_SCHEMA_GROUP_ITEM, SEQUENCE_TARGET))
        else:
            # 3) 查找序列插入 group 槽
            _insert_group_slot(conn, SEQUENCE_TARGET, group_schema_id)

        conn.commit()
        print('[v153] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v153] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v153 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True

        if not _factor_exists(conn, GROUP_FACTOR[0], GROUP_FACTOR[1]):
            print('[v153 verify] FAIL: 因子 %s/%s 缺失'
                  % (GROUP_FACTOR[0], GROUP_FACTOR[1]))
            ok = False

        schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_GROUP_ITEM)
        if not schema_id:
            print('[v153 verify] FAIL: 键表 %s 缺失' % KEY_SCHEMA_GROUP_ITEM)
            ok = False
        elif _schema_fields(conn, schema_id) != KEY_SCHEMA_GROUP_ITEM_FIELDS:
            print('[v153 verify] FAIL: 键表 %s 字段不符' % KEY_SCHEMA_GROUP_ITEM)
            ok = False

        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_TARGET)
        if not sequence_id:
            print('[v153 verify] FAIL: 查找序列 %s 缺失' % SEQUENCE_TARGET)
            ok = False
        else:
            steps = _load_steps(conn, sequence_id)
            ids = [(s or {}).get('key_schema_id') for s in steps]
            if schema_id and schema_id not in ids:
                print('[v153 verify] FAIL: 序列 %s 未含 group 槽'
                      % SEQUENCE_TARGET)
                ok = False
            seqs = sorted((s or {}).get('seq') for s in steps)
            if seqs != list(range(1, len(steps) + 1)):
                print('[v153 verify] FAIL: 序列 %s 的 seq 不连续或重复: %s'
                      % (SEQUENCE_TARGET, seqs))
                ok = False

        print('[v153 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v153 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        schema_id = _code_id(conn, 'key_schemas', KEY_SCHEMA_GROUP_ITEM)

        # 1) 序列去掉 group 槽并重排
        sequence_id = _code_id(conn, 'lookup_sequences', SEQUENCE_TARGET)
        if sequence_id and schema_id:
            steps = _load_steps(conn, sequence_id)
            if any((s or {}).get('key_schema_id') == schema_id for s in steps):
                kept = [dict(s or {}) for s in steps
                        if (s or {}).get('key_schema_id') != schema_id]
                kept.sort(key=lambda s: s.get('seq') or 0)
                restored = []
                for index, step in enumerate(kept, start=1):
                    step['seq'] = index
                    restored.append(step)
                conn.execute(
                    "UPDATE lookup_sequences SET steps = ?,"
                    " updated_at = datetime('now') WHERE id = ?",
                    (json.dumps(restored), sequence_id))
                print('  - [SEQ] %s 去掉 group 槽' % SEQUENCE_TARGET)
            else:
                print('  - [SKIP] 序列 %s 无 group 槽' % SEQUENCE_TARGET)

        # 2) 删除 group 键表（仍被价目行引用则保留）
        if schema_id:
            used = _one(conn, 'SELECT COUNT(1) FROM rate_records'
                        ' WHERE key_schema_id = ?', (schema_id,)) or 0
            if used:
                print('  - [WARN] 键表 %s 仍被 %d 行引用，保留'
                      % (KEY_SCHEMA_GROUP_ITEM, used))
            else:
                conn.execute('DELETE FROM key_schemas WHERE id = ?',
                             (schema_id,))
                print('  - [DEL] 键表 %s' % KEY_SCHEMA_GROUP_ITEM)

        # 3) 删除因子
        if _factor_exists(conn, GROUP_FACTOR[0], GROUP_FACTOR[1]):
            conn.execute('DELETE FROM factor_catalogs '
                         'WHERE object_type = ? AND field_id = ?',
                         (GROUP_FACTOR[0], GROUP_FACTOR[1]))
            print('  - [DEL] 因子 %s/%s' % (GROUP_FACTOR[0], GROUP_FACTOR[1]))

        conn.commit()
        print('[v153 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v153 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)
