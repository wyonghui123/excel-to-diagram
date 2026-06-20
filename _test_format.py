t = "引用的{target_name} '{value}' 不存在（字段：{field_name}）"
try:
    r = t.format(target_name='关联对象', value='')
    print(f"FORMAT OK: {r!r}")
except KeyError as e:
    print(f"KeyError: {e}")
print("---")
try:
    r = t.format(target_name='关联对象', value='', field_name='xxx')
    print(f"FULL: {r!r}")
except KeyError as e:
    print(f"KeyError: {e}")