"""重置 admin 密码为 admin123"""
import sqlite3
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from meta.services.auth_provider import _hash_password_pbdkdf2

new_hash = _hash_password_pbdkdf2('admin123')
print(f'new hash: {new_hash[:60]}...')

conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("UPDATE users SET password_hash = ?, must_change_password = 0 WHERE username = 'admin'", (new_hash,))
conn.commit()
print(f'updated rows: {cur.rowcount}')
conn.close()
