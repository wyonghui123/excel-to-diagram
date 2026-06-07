import sqlite3, hashlib
c = sqlite3.connect(r'd:\filework\excel-to-diagram\meta\architecture.db')
r = c.execute('PRAGMA integrity_check').fetchone()
print('Integrity:', r[0] if r else 'FAIL')
pw = hashlib.sha256('admin123'.encode()).hexdigest()
c.execute("UPDATE users SET password_hash=?, status='active' WHERE username='admin'", (pw,))
c.commit()
print('Admin OK')
c.close()
