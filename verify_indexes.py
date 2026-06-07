import sys
sys.path.insert(0, '.')
from meta.core.yaml_loader import register_from_directory, get_yaml_schema_dir
from meta.core.models import registry as meta_registry
from meta.core.index_rule_engine import IndexRuleEngine

schema_dir = get_yaml_schema_dir()
register_from_directory(schema_dir)

rule_engine = IndexRuleEngine()

for obj_name in ['enum_value', 'domain', 'sub_domain', 'service_module', 'business_object']:
    obj = meta_registry.get(obj_name)
    if obj:
        indexes = rule_engine.derive_indexes(obj)
        unique_indexes = [idx for idx in indexes if idx.unique]
        print(f"\n{obj_name} unique indexes:")
        for idx in unique_indexes:
            print(f"  - {idx.name}: {idx.fields}")
