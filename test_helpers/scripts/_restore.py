import os, sqlite3, hashlib, shutil

target = r'd:\filework\excel-to-diagram\meta\architecture.db'
source = r'd:\filework\excel-to-diagram\meta\architecture.db.baseline'

# Remove target and WAL files completely
for ext in ['', '-wal', '-shm']:
    path = target + ext
    for attempt in range(3):
        try:
            if os.path.exists(path):
                os.remove(path)
            break
        except PermissionError:
            import time
            time.sleep(0.5)

# Copy
shutil.copy2(source, target)
print('Copied from baseline')

# Verify
c = sqlite3.connect(target)
r = c.execute('PRAGMA integrity_check').fetchone()
print('Integrity:', r[0])

# Fix admin
pw = hashlib.sha256('admin123'.encode()).hexdigest()
c.execute("UPDATE users SET password_hash=?, status='active' WHERE username='admin'", (pw,))
c.commit()
print('Admin fixed')

row = c.execute("SELECT id, username, status FROM users WHERE username='admin'").fetchone()
print('Admin:', row)
c.close()
