import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

cursor = ds.execute("SELECT id, name, visibility, owner_id FROM products WHERE id = 475", [])
row = cursor.fetchone()
print(f'Product id=475: id={row[0]} name={row[1]} visibility={row[2]} owner_id={row[3]}')

# Check how many products match: id=475 AND (visibility='public' OR owner_id=3371)
cursor = ds.execute("SELECT COUNT(*) FROM products WHERE id = 475 AND (visibility = 'public' OR owner_id = 3371)", [])
count = cursor.fetchone()[0]
print(f'Products matching id=475 AND (visibility=public OR owner_id=3371): {count}')

# Check how many products match: id=475
cursor = ds.execute("SELECT COUNT(*) FROM products WHERE id = 475", [])
count = cursor.fetchone()[0]
print(f'Products matching id=475: {count}')
