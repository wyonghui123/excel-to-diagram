"""Remove debug prints from config_driven_hierarchy_filter.py"""
with open('d:/filework/excel-to-diagram/meta/services/config_driven_hierarchy_filter.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

cleaned = []
skip_next = False
for i, line in enumerate(lines):
    if 'print(f"[build_child_chain]' in line:
        continue
    if 'print(f"[TraverseDown]' in line:
        continue
    if 'print(f"[_query_child_ids]' in line:
        continue
    if 'print(f"[get_objects_by_dimension]' in line:
        continue
    if skip_next and line.strip() == '':
        skip_next = False
        continue
    if line.strip() == '' and i > 0 and lines[i-1].strip() == '':
        skip_next = True
        continue
    cleaned.append(line)

with open('d:/filework/excel-to-diagram/meta/services/config_driven_hierarchy_filter.py', 'w', encoding='utf-8') as f:
    f.writelines(cleaned)

print("Done!")
