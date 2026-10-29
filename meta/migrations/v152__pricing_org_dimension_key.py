# -*- coding: utf-8 -*-
"""[v152] 销售组织（org_id）进入定价匹配键（T2.2 / B8）

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md（组织维度价目键）
  · 波次 2 的客户维度（v130）只解决了「客户 × 物料」，同表内多组织的
    同物料同客户价无法区分 —— 组织维度此前只体现在 `rate_tables.owner_org_id`
    的**表级可见性**（`IS NULL OR = sales_org_id`），选表后同表内多条记录
    仍会串到别的组织。

范围（同一迁移内完成，幂等）:
  1. factor_catalogs   增 (sales_order_line, org_id) 因子
  2. key_schemas       增 KS_ORG_ITEM（["org_id","item_id"]）
                      增 KS_ORG_CUST_ITEM（["org_id","customer_account_id","item_id"]）
  3. lookup_sequences  LK_ITEM_STD 首槽插入 KS_ORG_ITEM（原槽位顺延）
                      LK_ITEM_CUST 首槽插入 KS_ORG_CUST_ITEM（原槽位顺延）
  4. rate_records      组织归属表（rate_tables.owner_org_id 非空）的存量记录：
                         · keys{} 补 `org_id = owner_org_id`（已存在则覆盖为表归属）
                         · key_schema_id 换成 org 版（原键已含 org 则不动）
  5. 服务注入（不在本迁移内）: determine_line 把 sales_org_id 传成槽位值 `org_id`

口径:
  · 键表只做「追加 org_id 前缀」，字段集合 = 原字段集合 ∪ {org_id}；
    未识别的键（不含 item_id 的组合）不换表，只补 keys 并打印告警。
  · 查找序列只插首槽并重排 seq（1..n），不改槽位所用键表 —— 引擎按
    `key_schema_id` 先粗筛，故「无组织值的单据」首槽置 None 被跳过，
    自然落回原物料/客户槽，零回归。
  · 存量记录 keys 的 org 值与表归属不一致时以 `owner_org_id` 为准（表是
    组织作用域的唯一真相源）。

幂等:
  · 因子按 (object_type, field_id) 判存在；键表按 code 判存在；
  · 序列首槽已是 org 键表则 SKIP；否则整体重排（重复执行终态一致）；
  · 回填按「keys 已有相同 org + 键表已含 org」判无需改动，只 UPDATE 有差异行。

回滚:
  序列去掉首槽并重排 → 键表还原（KS_ORG_* → KS_ITEM / KS_ITEM_CUST）
  → 删除 keys.org_id → 删除两张 org 键表 → 删除因子。
  无法还原「原本就带 org 的键」的原键表信息（迁移未留存），故回滚只做
  已识别映射的逆操作。
"""
import json
import sqlite3
import sys
from pathlib import Path

#: (object_type, field_id, source_type, is_price_relevant, description)
ORG_FACTOR = ('sales_order_line', 'org_id', 'static', 1,
              '销售组织：定价匹配键的组织维度（组织价按 org_id 区分）')

KEY_SCHEMA_ORG_ITEM = 'KS_ORG_ITEM'
KEY_SCHEMA_ORG_ITEM_FIELDS = ['org_id', 'item_id']
KEY_SCHEMA_ORG_ITEM_NAME = '组织×物料匹配键'

KEY_SCHEMA_ORG_CUST_ITEM = 'KS_ORG_CUST_ITEM'
KEY_SCHEMA_ORG_CUST_ITEM_FIELDS = ['org_id', 'customer_account_id', 'item_id']
KEY_SCHEMA_ORG_CUST_ITEM_NAME = '组织×客户×物料匹配键'

#: 原键表编码（回滚时还原用）
BASE_ITEM_KEY_SCHEMA = 'KS_ITEM'
BASE_ITEM_KEY_CUST_SCHEMA = 'KS_ITEM_CUST'

#: 查找序列 → 首槽组织的键表编码
SEQUENCE_TARGETS = (
    ('LK_ITEM_STD', KEY_SCHEMA_ORG_ITEM),
    ('LK_ITEM_CUST', KEY_SCHEMA_ORG_CUST_ITEM),
)

#: 原键字段集合（frozenset）→ org 版键表编码。只有字段集合完全匹配才换表。
FIELD_MAPPINGS = {
    frozenset(['item_id']): KEY_SCHEMA_ORG_ITEM,
    frozenset(['customer_account_id', 'item_id']): KEY_SCHEMA_ORG_CUST_ITEM,
}

#: 回滚：org 版键表 → 原键表编码
ROLLBACK_MAPPINGS = {
    KEY_SCHEMA_ORG_ITEM: BASE_ITEM_KEY_SCHEMA,
    KEY_SCHEMA_ORG_CUST_ITEM: BASE_ITEM_KEY_CUST_SCHEMA,
}

REQUIRED_TABLES = ('factor_catalogs', 'key_schemas', 'lookup_sequences',
                   'rate_tables', 'rate_records')


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


def _prepend_org_slot(conn, sequence_code, org_schema_id):
    """把 org 键表插为首槽；已有同首槽则跳过。返回是否发生改动。"""
    sequence_id = _code_id(conn, 'lookup_sequences', sequence_code)
    if not sequence_id:
        print('  - [SKIP] 查找序列 %s 不存在（波次 2 未点亮？）' % sequence_code)
        return False
    steps = _load_steps(conn, sequence_id)
    if not steps:
        print('  - [SKIP] 查找序列 %s 槽位为空' % sequence_code)
        return False
    if (steps[0] or {}).get('key_schema_id') == org_schema_id:
        print('  - [SKIP] 查找序列 %s 首槽已是 org 键' % sequence_code)
        return False

    ordered = sorted(steps, key=lambda s: (s or {}).get('seq') or 0)
    new_steps = [{'seq': 1, 'key_schema_id': org_schema_id}]
    for index, step in enumerate(ordered, start=2):
        shifted = dict(step or {})
        shifted['seq'] = index
        new_steps.append(shifted)
    conn.execute(
        "UPDATE lookup_sequences SET steps = ?, updated_at = datetime('now')"
        ' WHERE id = ?',
        (json.dumps(new_steps), sequence_id))
    print('  - [SEQ] %s 首槽 → %s（原 %d 槽顺延）'
          % (sequence_code, org_schema_id, len(ordered)))
    return True


def _backfill_rate_records(conn, org_schema_ids):
    """把组织归属表的存量价目行补上 org_id 维度。返回 (改动数, 跳过数, 告警数)。"""
    rows = conn.execute(
        'SELECT r.id, r.keys, r.key_schema_id, t.owner_org_id'
        '  FROM rate_records r'
        '  JOIN rate_tables t ON t.id = r.rate_table_id'
        ' WHERE t.owner_org_id IS NOT NULL').fetchall()
    changed = skipped = warned = 0
    for record_id, raw_keys, schema_id, owner in rows:
        try:
            keys = json.loads(raw_keys or '{}')
        except (TypeError, ValueError):
            keys = {}
        if not isinstance(keys, dict):
            keys = {}

        fields = _schema_fields(conn, schema_id)
        target_schema = schema_id
        if 'org_id' not in fields:
            mapped = FIELD_MAPPINGS.get(frozenset(fields))
            if mapped and org_schema_ids.get(mapped):
                target_schema = org_schema_ids[mapped]
            else:
                print('  - [WARN] 价目行 %s 的键字段 %s 无法自动加 org，'
                      '仅补 keys' % (record_id, fields))
                warned += 1

        new_keys = dict(keys)
        new_keys['org_id'] = owner
        if new_keys == keys and target_schema == schema_id:
            skipped += 1
            continue

        conn.execute(
            "UPDATE rate_records SET keys = ?, key_schema_id = ?,"
            " updated_at = datetime('now') WHERE id = ?",
            (json.dumps(new_keys), target_schema, record_id))
        changed += 1
    if changed:
        print('  - [BACKFILL] rate_records: %d 行（跳过 %d，告警 %d）'
              % (changed, skipped, warned))
    else:
        print('  - [SKIP] 价目行回填：无需改动（%d 行已带 org，告警 %d）'
              % (skipped, warned))
    return changed, skipped, warned


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v152] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v152] 开始: 销售组织进入定价匹配键')
        missing = [t for t in REQUIRED_TABLES if not _table_exists(conn, t)]
        if missing:
            print('  - [FAIL] 缺表 %s' % missing)
            return False

        now = "datetime('now')"

        # 1) 因子
        object_type, field_id, source_type, relevant, desc = ORG_FACTOR
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

        # 2) 两张 org 键表
        for code, name, fields, note in (
            (KEY_SCHEMA_ORG_ITEM, KEY_SCHEMA_ORG_ITEM_NAME,
             KEY_SCHEMA_ORG_ITEM_FIELDS, '组织 × 物料：组织价优先，未命中落物料价'),
            (KEY_SCHEMA_ORG_CUST_ITEM, KEY_SCHEMA_ORG_CUST_ITEM_NAME,
             KEY_SCHEMA_ORG_CUST_ITEM_FIELDS,
             '组织 × 客户 × 物料：组织客户价优先'),
        ):
            if _code_id(conn, 'key_schemas', code):
                print('  - [SKIP] 键表 %s 已存在' % code)
            else:
                conn.execute(
                    'INSERT INTO key_schemas '
                    '(code, name, key_fields, description, created_at, updated_at) '
                    'VALUES (?, ?, ?, ?, %s, %s)' % (now, now),
                    (code, name, json.dumps(fields), note))
                print('  - [KS] + %s' % code)

        org_schema_ids = {
            code: _code_id(conn, 'key_schemas', code)
            for code in (KEY_SCHEMA_ORG_ITEM, KEY_SCHEMA_ORG_CUST_ITEM)
        }

        # 3) 查找序列首槽插入 org 键
        for sequence_code, schema_code in SEQUENCE_TARGETS:
            schema_id = org_schema_ids.get(schema_code)
            if not schema_id:
                print('  - [FAIL] 键表 %s 缺失，跳过序列 %s'
                      % (schema_code, sequence_code))
                continue
            _prepend_org_slot(conn, sequence_code, schema_id)

        # 4) 组织归属表存量价目行回填
        _backfill_rate_records(conn, org_schema_ids)

        conn.commit()
        print('[v152] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v152] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v152 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True

        if not _factor_exists(conn, ORG_FACTOR[0], ORG_FACTOR[1]):
            print('[v152 verify] FAIL: 因子 %s/%s 缺失'
                  % (ORG_FACTOR[0], ORG_FACTOR[1]))
            ok = False

        for code, fields in ((KEY_SCHEMA_ORG_ITEM, KEY_SCHEMA_ORG_ITEM_FIELDS),
                             (KEY_SCHEMA_ORG_CUST_ITEM,
                              KEY_SCHEMA_ORG_CUST_ITEM_FIELDS)):
            schema_id = _code_id(conn, 'key_schemas', code)
            if not schema_id:
                print('[v152 verify] FAIL: 键表 %s 缺失' % code)
                ok = False
                continue
            if _schema_fields(conn, schema_id) != fields:
                print('[v152 verify] FAIL: 键表 %s 字段不符' % code)
                ok = False

        for sequence_code, schema_code in SEQUENCE_TARGETS:
            sequence_id = _code_id(conn, 'lookup_sequences', sequence_code)
            if not sequence_id:
                continue        # 序列不存在 = 该波次未点亮，不算失败
            schema_id = _code_id(conn, 'key_schemas', schema_code)
            steps = _load_steps(conn, sequence_id)
            if not steps or steps[0].get('key_schema_id') != schema_id:
                print('[v152 verify] FAIL: 序列 %s 首槽不是 %s'
                      % (sequence_code, schema_code))
                ok = False

        # 存量：组织归属表的每一行都必须带与表归属一致的 org_id
        rows = conn.execute(
            'SELECT r.id, r.keys, r.key_schema_id, t.owner_org_id'
            '  FROM rate_records r'
            '  JOIN rate_tables t ON t.id = r.rate_table_id'
            ' WHERE t.owner_org_id IS NOT NULL').fetchall()
        for record_id, raw_keys, schema_id, owner in rows:
            try:
                keys = json.loads(raw_keys or '{}')
            except (TypeError, ValueError):
                keys = {}
            if not isinstance(keys, dict) or keys.get('org_id') != owner:
                print('[v152 verify] FAIL: 价目行 %s keys 缺 org_id=%r'
                      % (record_id, owner))
                ok = False
            if 'org_id' not in _schema_fields(conn, schema_id):
                print('[v152 verify] FAIL: 价目行 %s 键表未含 org_id'
                      % (record_id,))
                ok = False

        print('[v152 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v152 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        # 1) 序列去掉 org 首槽并重排
        for sequence_code, _schema_code in SEQUENCE_TARGETS:
            sequence_id = _code_id(conn, 'lookup_sequences', sequence_code)
            if not sequence_id:
                continue
            steps = _load_steps(conn, sequence_id)
            if not steps or 'org_id' not in _schema_fields(
                    conn, (steps[0] or {}).get('key_schema_id')):
                print('  - [SKIP] 序列 %s 首槽非 org 键' % sequence_code)
                continue
            kept = sorted(steps[1:], key=lambda s: (s or {}).get('seq') or 0)
            restored = []
            for index, step in enumerate(kept, start=1):
                shifted = dict(step or {})
                shifted['seq'] = index
                restored.append(shifted)
            conn.execute(
                "UPDATE lookup_sequences SET steps = ?, updated_at = datetime('now')"
                ' WHERE id = ?', (json.dumps(restored), sequence_id))
            print('  - [SEQ] %s 去掉 org 首槽' % sequence_code)

        # 2) 存量价目行：去掉 org_id 并还原键表
        rows = conn.execute(
            'SELECT r.id, r.keys, r.key_schema_id'
            '  FROM rate_records r'
            '  JOIN rate_tables t ON t.id = r.rate_table_id'
            ' WHERE t.owner_org_id IS NOT NULL').fetchall()
        for record_id, raw_keys, schema_id in rows:
            try:
                keys = json.loads(raw_keys or '{}')
            except (TypeError, ValueError):
                keys = {}
            if not isinstance(keys, dict) or 'org_id' not in keys:
                continue
            keys.pop('org_id', None)
            schema_code = _one(conn, 'SELECT code FROM key_schemas WHERE id = ?',
                               (schema_id,))
            target_schema = schema_id
            base_code = ROLLBACK_MAPPINGS.get(schema_code)
            if base_code:
                target_schema = _code_id(conn, 'key_schemas', base_code) or schema_id
            conn.execute(
                "UPDATE rate_records SET keys = ?, key_schema_id = ?,"
                " updated_at = datetime('now') WHERE id = ?",
                (json.dumps(keys), target_schema, record_id))

        # 3) 删除两张 org 键表（仍被引用则保留）
        for code in (KEY_SCHEMA_ORG_ITEM, KEY_SCHEMA_ORG_CUST_ITEM):
            schema_id = _code_id(conn, 'key_schemas', code)
            if not schema_id:
                continue
            used = _one(conn, 'SELECT COUNT(1) FROM rate_records WHERE key_schema_id = ?',
                        (schema_id,)) or 0
            if used:
                print('  - [WARN] 键表 %s 仍被 %d 行引用，保留' % (code, used))
                continue
            conn.execute('DELETE FROM key_schemas WHERE id = ?', (schema_id,))
            print('  - [DEL] 键表 %s' % code)

        # 4) 删除因子
        if _factor_exists(conn, ORG_FACTOR[0], ORG_FACTOR[1]):
            conn.execute('DELETE FROM factor_catalogs '
                         'WHERE object_type = ? AND field_id = ?',
                         (ORG_FACTOR[0], ORG_FACTOR[1]))
            print('  - [DEL] 因子 %s/%s' % (ORG_FACTOR[0], ORG_FACTOR[1]))

        conn.commit()
        print('[v152 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v152 rollback] 失败: %s' % e)
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
