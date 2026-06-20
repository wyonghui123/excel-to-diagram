import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from meta.core.models import registry
registry.reload('d:/filework/excel-to-diagram/meta/schemas')
obj = registry.get('relationship')
for f in obj.fields:
    if f.id in ('source_bo_id','target_bo_id','source_code','target_code','source_bo_code','source_domain_id'):
        sem = getattr(f, 'semantics', None)
        vh = getattr(f, 'value_help', None)
        ui = getattr(f, 'ui', None)
        print(f"{f.id}: type={f.field_type.value}, storage={getattr(f.storage,'value',None)}, resolve_from={getattr(sem,'resolve_from_field',None)}, resolve_to={getattr(sem,'resolve_to_object',None)}, ui.editable={getattr(ui,'editable',None)}, sem.import_visible={getattr(sem,'import_visible',None)}, vh_target={getattr(getattr(vh,'source',None),'target_bo',None)}, vh_code_field={getattr(getattr(vh,'source',None),'code_field',None)}")
