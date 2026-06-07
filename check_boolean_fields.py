import os
import re
from pathlib import Path

schema_dir = Path('meta/schemas')

issues = []
boolean_fields = []

for yaml_file in schema_dir.glob('*.yaml'):
    content = yaml_file.read_text(encoding='utf-8')
    lines = content.split('\n')
    
    # Find boolean fields
    current_field_id = None
    current_field_name = None
    in_fields = False
    
    for i, line in enumerate(lines):
        # Track field definitions
        if line.strip().startswith('- id:'):
            current_field_id = line.split(':', 1)[1].strip()
        elif line.strip().startswith('name:') and current_field_id:
            current_field_name = line.split(':', 1)[1].strip()