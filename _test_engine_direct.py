"""Direct test of auto_detect_start and preview_code"""
import sys
sys.path.insert(0, r'd:\filework\excel-to-diagram')

from meta.core.datasource import get_data_source
from meta.core.key_template_engine import KeyTemplateEngine, KeyTemplateConfig

# Use the same data source as the backend
ds = get_data_source("sqlite", database=r'd:\filework\excel-to-diagram\data\arch.db')

engine = KeyTemplateEngine(ds)

# Test auto_detect_start directly
result = engine._sequence_engine.auto_detect_start(
    "bo_code_seq:PROC_REQ_MNG", "business_object", "code"
)
print(f"auto_detect_start result: {result}")

# Build a config like business_object.yaml
config_dict = {
    "enabled": True,
    "auto_suggest": True,
    "pattern": "{service_module_code}{SEQ:2}",
    "segments": [
        {"type": "parent_field", "source": "service_module_code", "transform": "upper"},
        {"type": "sequence", "name": "bo_code_seq", "scope": "service_module_code",
         "auto_detect": True, "padding": 2, "start": 1}
    ]
}
config = KeyTemplateConfig.from_dict("business_object", config_dict)

# Test preview_code
field_values = {"service_module_code": "PROC_REQ_MNG"}
code = engine.preview_code(config, field_values)
print(f"preview_code result: {code}")

# Test generate_code
code = engine.generate_code(config, field_values, "business_object")
print(f"generate_code result: {code}")