import json
# 模拟后端按 enabled_with_idx 顺序填入 dict
d = {}
d['domain'] = {'c': 0, 'u': 2}
d['sub_domain'] = {'c': 0, 'u': 7}
d['service_module'] = {'c': 0, 'u': 10}
d['business_object'] = {'c': 1, 'u': 9}
d['relationship'] = {'c': 0, 'u': 34, 'f': 1}
d['annotation'] = {'c': 0, 'u': 24}
# 检查内存顺序
print('内存 key 顺序:', list(d.keys()))
print()
print('json.dumps 输出:')
print(json.dumps(d, ensure_ascii=False, indent=2))