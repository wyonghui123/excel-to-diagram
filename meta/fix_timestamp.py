import sqlite3
from datetime import datetime

conn = sqlite3.connect('d:/filework/excel-to-diagram/meta/architecture.db')
cursor = conn.cursor()

now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# 修复 ID=7 (asdf) 的时间戳
cursor.execute(
    "UPDATE user_groups SET created_at = ?, updated_at = ? WHERE id = 7",
    [now, now]
)
print(f'Updated ID=7 with timestamp: {now}')

# 验证
cursor.execute('SELECT id, name, created_at, updated_at FROM user_groups ORDER BY id')
for row in cursor.fetchall():
    print(f'ID={row[0]}, name={row[1]}, created_at={repr(row[2])}, updated_at={repr(row[3])}')

conn.commit()
conn.close()
