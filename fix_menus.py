import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.services.menu_auto_generator import menu_auto_generator
from meta.core.datasource import get_data_source

db_path = 'd:/filework/excel-to-diagram/architecture.db'
ds = get_data_source('sqlite', database=db_path)

try:
    count = menu_auto_generator.persist_to_db(ds)
    print(f"Persisted {count} menus to database")
except Exception as e:
    print(f"Error: {e}")
