import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.models import registry
from meta.core.bo_framework import BOFramework
from meta.core.datasource import get_data_source
import os

# 强制重新加载
from meta.core.models import MetaRegistry
MetaRegistry.__force_reload__ = True

# 清除缓存
from meta.core import yaml_loader
yaml_loader._dir_registry_cache.clear()
yaml_loader._yaml_cache.clear()

# 重新加载
schema_dir = get_yaml_schema_dir()
register_from_directory(schema_dir)

# 获取 domain 的 schema
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'meta', 'architecture.db')
ds = get_data_source("sqlite", database=db_path)
bo_framework = BOFramework(ds)

schema = bo_framework.get_schema('domain')
for field in schema.get('fields', []):
    if field.get('id') == 'version_id':
        vh = field.get('value_help', {})
        multiple = vh.get('behavior', {}).get('multiple')
        print(f"version_id value_help.behavior.multiple = {multiple}")
        print(f"Full value_help: {vh}")
        break
