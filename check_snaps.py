import os, sqlite3, glob

test_temp = r'd:\filework\test_temp'
snapshots = sorted(glob.glob(test_temp + r'\architecture_snapshot_*.db'))
print(f'Total snapshots: {len(snapshots)}')

for snap in snapshots[-5:]:
    size = os.path.getsize(snap)
    try:
        conn = sqlite3.connect(snap)
        r = conn.execute('PRAGMA integrity_check').fetchone()[0]
        tables = conn.execute('SELECT count(*) FROM sqlite_master WHERE type="table"').fetchone()[0]
        conn.close()
        print(f'{os.path.basename(snap)}: size={size} integrity={r} tables={tables}')
    except Exception as e:
        print(f'{os.path.basename(snap)}: size={size} ERROR={e}')
