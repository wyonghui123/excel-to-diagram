"""Find correct DB path and table name"""
import sys
sys.path.insert(0, r'd:\filework\excel-to-diagram')
from meta.core.datasource import get_data_source

# Check default paths
import os
candidates = [
    r'd:\filework\excel-to-diagram\data\arch.db',
    r'd:\filework\excel-to-diagram\data\excel_to_diagram.db',
    r'd:\filework\excel-to-diagram\arch.db',
]
for path in candidates:
    if os.path.exists(path):
        print(f"Found: {path}")

# Use the first found
for path in candidates:
    if os.path.exists(path):
        ds = get_data_source("sqlite", database=path)
        cur = ds.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [r[0] if isinstance(r, tuple) else r.get('name') for r in cur.fetchall()]
        bo_tables = [t for t in tables if 'business' in t.lower()]
        print(f"\nBusiness tables: {bo_tables}")
        print(f"All tables (first 20): {tables[:20]}")

        # Check bo count
        for t in bo_tables:
            try:
                c = ds.execute(f"SELECT COUNT(*) FROM {t}")
                count = c.fetchone()[0]
                print(f"  {t}: {count} rows")
                if count > 0 and count < 50:
                    c = ds.execute(f"SELECT id, code, service_module_id FROM {t}")
                    for row in c.fetchall()[:5]:
                        print(f"    {row}")
            except Exception as e:
                print(f"  {t}: error {e}")
        break