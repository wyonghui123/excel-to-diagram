"""[FIX v1.2.52 2026-06-22] 清理历史悬空 annotation

历史 bug: 以前删除主对象时 cascade interceptor 未生效,导致 89 条
annotation 变成悬空记录 (target_id 找不到主对象)。导出 Excel 时这些
悬空记录的"关联对象编码/名称"为 None,显示为空。

当前 cascade 代码已正常 (transaction 一起 commit/rollback),只是历史
垃圾需要清理。

[WARNING] 此脚本会真实删除 89 条 annotation,执行前先备份:
  cp meta/architecture.db meta/architecture.db.pre_orphan_cleanup
"""
import sqlite3
import shutil
import os
import sys
from datetime import datetime

DB = r'd:\filework\excel-to-diagram\meta\architecture.db'
BACKUP = DB + '.pre_orphan_cleanup_' + datetime.now().strftime('%Y%m%d_%H%M%S')

print("=" * 60)
print("清理历史悬空 annotation")
print("=" * 60)

# 1. 备份
print(f"\n[1/4] 备份数据库 → {BACKUP}")
shutil.copy2(DB, BACKUP)
print(f"  完成 (size={os.path.getsize(BACKUP)})")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 2. 统计悬空记录
print(f"\n[2/4] 扫描悬空 annotation")
orphan_query = '''
SELECT a.id, a.target_type, a.target_id, a.category, a.content
FROM annotations a
WHERE NOT EXISTS (
    SELECT 1 FROM business_objects b WHERE b.id = a.target_id AND a.target_type = 'business_object'
)
AND NOT EXISTS (
    SELECT 1 FROM relationships r WHERE r.id = a.target_id AND a.target_type = 'relationship'
)
AND NOT EXISTS (
    SELECT 1 FROM service_modules s WHERE s.id = a.target_id AND a.target_type = 'service_module'
)
AND NOT EXISTS (
    SELECT 1 FROM sub_domains sd WHERE sd.id = a.target_id AND a.target_type = 'sub_domain'
)
AND NOT EXISTS (
    SELECT 1 FROM domains d WHERE d.id = a.target_id AND a.target_type = 'domain'
)
ORDER BY a.target_type, a.id
'''
orphan_rows = cur.execute(orphan_query).fetchall()
print(f"  悬空记录数: {len(orphan_rows)}")

# 按 target_type 分组统计
type_counts = {}
for r in orphan_rows:
    type_counts[r[1]] = type_counts.get(r[1], 0) + 1
for t, n in type_counts.items():
    print(f"    {t}: {n}")

if not orphan_rows:
    print("  无悬空记录,无需清理")
    conn.close()
    sys.exit(0)

# 3. 确认并删除
print(f"\n[3/4] 删除 {len(orphan_rows)} 条悬空 annotation")
orphan_ids = [r[0] for r in orphan_rows]
placeholders = ','.join('?' * len(orphan_ids))
delete_sql = f"DELETE FROM annotations WHERE id IN ({placeholders})"
cur.execute(delete_sql, orphan_ids)
deleted_count = cur.rowcount
conn.commit()
print(f"  实际删除: {deleted_count} 条")

# 4. 复检
print(f"\n[4/4] 复检")
remaining = cur.execute("SELECT COUNT(*) FROM annotations").fetchone()[0]
print(f"  剩余 annotation 总数: {remaining}")
remaining_orphan = cur.execute(orphan_query).fetchall()
print(f"  剩余悬空: {len(remaining_orphan)}")

# 也要清理 audit_logs 里这些 annotation 的引用 (可选)
print()
print("=" * 60)
print(f"完成: 删除 {deleted_count} 条, 剩余 {remaining} 条")
print(f"备份: {BACKUP}")
print("=" * 60)

conn.close()
