"""Debug auto_detect_start"""
import sys
sys.path.insert(0, r'd:\filework\excel-to-diagram')

from meta.core.datasource import get_data_source
from meta.core.key_template_engine import KeyTemplateEngine

ds = get_data_source("sqlite", database=r'd:\filework\excel-to-diagram\data\arch.db')

# Direct SQL
print("=== Direct SQL ===")
cursor = ds.execute("SELECT code FROM business_object")
rows = cursor.fetchall()
print(f"Total rows: {len(rows)}")
import re
trailing_digits = re.compile(r'(\d+)\s*$')
max_val = 0
for row in rows:
    code = row[0] if isinstance(row, (tuple, list)) else row.get('code')
    m = trailing_digits.search(str(code))
    if m:
        v = int(m.group(1))
        if v > max_val:
            max_val = v
print(f"Max trailing digit: {max_val}")

# Now via engine
engine = KeyTemplateEngine(ds)
result = engine._sequence_engine.auto_detect_start(
    "bo_code_seq:PROC_REQ_MNG", "business_object", "code"
)
print(f"engine.auto_detect_start result: {result}")