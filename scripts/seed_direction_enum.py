"""把 direction 枚举的 3 个值写入 enum_values 表。

Bug: 关系详情页 '关系方向' 显示 BIDIRECTIONAL/PUSH/PULL (key) 而非中文名。
根因: yaml schema 引用了 enum_type_id='direction'，但 enum_values 表无对应数据，
      UIConfigBuilder 之前只使用字段元数据的静态 enum_values，导致前端拿到 key。

执行: cd d:/filework/excel-to-diagram; python scripts/seed_direction_enum.py
"""
import sqlite3
import os
import sys

DB_PATH = 'meta/architecture.db'

# 方向枚举值（与 yaml 中允许的 PUSH/PULL/BIDIRECTIONAL 一致）
DIRECTION_VALUES = [
    ('PUSH',          '推送', 0, '数据从源对象推送到目标对象'),
    ('PULL',          '拉取', 1, '数据从目标对象拉取到源对象'),
    ('BIDIRECTIONAL', '双向', 2, '数据在源/目标之间双向流动'),
]


def seed():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 1) 确保 enum_types 里有 'direction'
    cur.execute("SELECT id FROM enum_types WHERE id = 'direction'")
    if not cur.fetchone():
        print("插入 enum_types.direction ...")
        cur.execute(
            "INSERT INTO enum_types (id, name, category, mutability, description, is_active) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ('direction', '关系方向', 'system', 'locked',
             '关系的数据流向方向 (PUSH/PULL/BIDIRECTIONAL)', 1)
        )
    else:
        print("enum_types.direction 已存在")

    # 2) 写入 enum_values (idempotent: ON CONFLICT 跳过)
    for code, name, sort_order, desc in DIRECTION_VALUES:
        cur.execute(
            "SELECT 1 FROM enum_values WHERE enum_type_id='direction' AND code=?", (code,))
        if cur.fetchone():
            print(f"  skip: {code} (已存在)")
            continue
        cur.execute(
            "INSERT INTO enum_values "
            "(enum_type_id, code, name, name_en, description, is_active, sort_order) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ('direction', code, name, name, desc, 1, sort_order)
        )
        print(f"  inserted: {code} -> {name}")

    con.commit()

    # 3) 校验
    print("\n=== 校验 enum_values.direction ===")
    cur.execute(
        "SELECT code, name, is_active, sort_order FROM enum_values "
        "WHERE enum_type_id='direction' ORDER BY sort_order"
    )
    for r in cur.fetchall():
        print(' ', r)
    con.close()


if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        print(f"DB 不存在: {DB_PATH}")
        sys.exit(1)
    seed()
    print("\n[OK] direction 枚举已就绪")
