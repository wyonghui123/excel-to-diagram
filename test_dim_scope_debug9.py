import sys, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
os.chdir('d:/filework/excel-to-diagram')

from meta.core.datasource import get_data_source
ds = get_data_source('sqlite', database='meta/architecture.db')

# Check how many products have owner_id = 3371
cursor = ds.execute("SELECT COUNT(*) FROM products WHERE owner_id = 3371", [])
count = cursor.fetchone()[0]
print(f'Products with owner_id=3371: {count}')

# Check how many products have owner_id = 3371 AND id != 475
cursor = ds.execute("SELECT id, name, owner_id FROM products WHERE owner_id = 3371 AND id != 475", [])
rows = cursor.fetchall()
print(f'Products with owner_id=3371 AND id!=475: {len(rows)}')
for r in rows[:5]:
    print(f'  id={r[0]} name={r[1]} owner_id={r[2]}')

# Total products
cursor = ds.execute("SELECT COUNT(*) FROM products", [])
total = cursor.fetchone()[0]
print(f'\nTotal products: {total}')

# Products with id=475
cursor = ds.execute("SELECT id, name, owner_id FROM products WHERE id = 475", [])
row = cursor.fetchone()
print(f'Product id=475: id={row[0]} name={row[1]} owner_id={row[2]}')
