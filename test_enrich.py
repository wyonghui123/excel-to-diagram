import sys
sys.path.insert(0, r'D:\filework\release-prep-worktree')
import sqlite3

# 直接用 sqlite3 连接 db, 模拟 ds.query 的行为
class FakeDS:
    def __init__(self, conn):
        self._conn = conn
        self._row_factory = sqlite3.Row

    def query(self, sql, params):
        cur = self._conn.execute(sql, params)
        cur.row_factory = sqlite3.Row
        return [dict(r) for r in cur.fetchall()]


conn = sqlite3.connect(r'D:\filework\release-prep-worktree\meta\architecture.db')
ds = FakeDS(conn)

from meta.core.audit_derived_fields import enrich_audit_virtual_fields

# 测试 relationship (一个真实存在的对象)
records = [
    {'id': 1, 'code': 'TEST_REL_1', 'created_at': '2026-01-01T00:00:00'},
    {'id': 2, 'code': 'TEST_REL_2', 'created_at': '2026-01-02T00:00:00'},
]

print('测试前 records:')
for r in records:
    print(f'  {r}')

result = enrich_audit_virtual_fields(
    ds=ds,
    object_type='relationship',
    records=records,
    field_ids=['updated_at'],
)

print('\n测试后 records:')
for r in result:
    print(f'  {r}')
    print(f'    updated_at present: {"updated_at" in r}')

conn.close()