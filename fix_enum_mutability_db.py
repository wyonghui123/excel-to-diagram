"""
修复 enum_types 表中 mutability 字段的错误值 (fully_editable → fullEditable)
"""
import sqlite3
import sys

DB_PATH = r'd:\filework\excel-to-diagram\meta\architecture.db'

# 历史值 → 正确值 的映射
VALUE_MAP = {
    'fully_editable': 'fullEditable',
    'mutable': 'fullEditable',
    'immutable': 'extensible',
    'frozen': 'locked',
}


def main(dry_run=True):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # 1. 扫描所有错误值
    print('=== 当前 mutability 分布 ===')
    for row in cur.execute("SELECT mutability, COUNT(*) FROM enum_types GROUP BY mutability"):
        print(f"  {row[0]!r}: {row[1]}")

    # 2. 列出需要修复的记录
    print('\n=== 需要修复的记录 ===')
    needs_fix = []
    for bad_val, good_val in VALUE_MAP.items():
        rows = cur.execute(
            "SELECT id, name, category, mutability FROM enum_types WHERE mutability = ?",
            (bad_val,)
        ).fetchall()
        for r in rows:
            print(f"  id={r[0]!r}, name={r[1]!r}, category={r[2]!r}, mutability={r[3]!r} → {good_val!r}")
            needs_fix.append((r[0], good_val))

    if not needs_fix:
        print('\n[OK] 无需修复')
        return

    if dry_run:
        print(f'\n[DRY-RUN] 共 {len(needs_fix)} 条记录待修复。执行 --execute 实际修复。')
        return

    # 3. 备份原值到临时表（用于回滚）
    print('\n=== 备份到 enum_types_mutability_backup ===')
    cur.execute("""
        CREATE TABLE IF NOT EXISTS enum_types_mutability_backup AS
        SELECT id, name, mutability, datetime('now') as backed_at
        FROM enum_types
        WHERE mutability IN ({})
    """.format(','.join('?' for _ in VALUE_MAP)), tuple(VALUE_MAP.keys()))

    # 4. 执行修复
    for enum_id, new_val in needs_fix:
        cur.execute("UPDATE enum_types SET mutability = ? WHERE id = ?", (new_val, enum_id))
        print(f"  [FIX] {enum_id}: mutability → {new_val!r}")

    conn.commit()

    # 5. 验证
    print('\n=== 修复后分布 ===')
    for row in cur.execute("SELECT mutability, COUNT(*) FROM enum_types GROUP BY mutability"):
        print(f"  {row[0]!r}: {row[1]}")

    # 6. 校验已无错误值
    remaining = cur.execute(
        f"SELECT COUNT(*) FROM enum_types WHERE mutability IN ({','.join('?' for _ in VALUE_MAP)})",
        tuple(VALUE_MAP.keys())
    ).fetchone()[0]
    print(f'\n[VERIFY] 剩余错误值记录数: {remaining}')
    if remaining == 0:
        print('[OK] 修复完成')
    else:
        print(f'[WARN] 仍有 {remaining} 条记录需要人工处理')

    conn.close()


if __name__ == '__main__':
    is_dry = '--execute' not in sys.argv
    main(dry_run=is_dry)
