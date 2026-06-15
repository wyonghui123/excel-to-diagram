"""Direct test using correct DB path"""
import sys
sys.path.insert(0, r'd:\filework\excel-to-diagram')
from meta.core.datasource import get_data_source
from meta.core.key_template_engine import KeyTemplateEngine, KeyTemplateConfig

ds = get_data_source("sqlite", database=r'd:\filework\excel-to-diagram\meta\architecture.db')
cur = ds.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [r[0] if isinstance(r, tuple) else r.get('name') for r in cur.fetchall()]
bo_tables = [t for t in tables if 'business' in t.lower()]
print(f"BO tables: {bo_tables}")

# Find which has PROC_REQ_MNG01
for t in bo_tables:
    c = ds.execute(f"SELECT id, code, service_module_id FROM {t} WHERE code LIKE 'PROC%'")
    rows = c.fetchall()
    print(f"\n{t} PROC rows:")
    for row in rows:
        print(f"  {row}")

# Now test auto_detect_start
engine = KeyTemplateEngine(ds)
print(f"\n=== auto_detect_start 测试 ===")
for t in bo_tables:
    result = engine._sequence_engine.auto_detect_start(
        "bo_code_seq:PROC_REQ_MNG", t, "code"
    )
    print(f"  {t}: max_seq={result}")