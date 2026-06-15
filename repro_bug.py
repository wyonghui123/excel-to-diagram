"""[REPRO] 复现 BUG：relationship preview 返回 MISSING_PARENT_FIELD"""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

from meta.core.key_template_engine import KeyTemplateConfig
from meta.api.key_template_api import _resolve_parent_fields_for_preview, _get_missing_parent_fields

# 模拟 relationship 配置
config = KeyTemplateConfig.from_dict('relationship', {
    'enabled': True,
    'user_editable': 'auto_or_manual',
    'auto_suggest': True,
    'pattern': '{source_code}-{target_code}-{SEQ:2}',
    'separator': '-',
    'segments': [
        {'type': 'parent_field', 'source': 'source_code'},
        {'type': 'separator', 'value': '-'},
        {'type': 'parent_field', 'source': 'target_code'},
        {'type': 'separator', 'value': '-'},
        {'type': 'sequence', 'name': 'rel_seq', 'scope': 'source_bo_id', 'padding': 2, 'start': 1}
    ]
})
print('config.pattern:', config.pattern)
print('config.segments:', config.segments)

field_values = {}
parent_params = {
    'source_bo_id': 468,
    'target_bo_id': 467,
}

print('\nBefore resolve:')
print('  field_values:', field_values)
print('  parent_params:', parent_params)

# 模拟 _resolve_parent_fields_for_preview
import re
field_refs = re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', config.pattern)
print('\nfield_refs in pattern:', field_refs)

# 直接 import 内部函数
from meta.api.key_template_api import _engine
print('engine:', _engine)
if _engine:
    _resolve_parent_fields_for_preview(config, field_values, parent_params)
    print('\nAfter resolve:')
    print('  field_values:', field_values)
    missing = _get_missing_parent_fields(config, field_values)
    print('  missing fields:', missing)
else:
    print('No engine available')