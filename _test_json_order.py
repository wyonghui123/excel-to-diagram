import json
d = {}
d['domain'] = 1
d['sub_domain'] = 2
d['annotation'] = 3
d['relationship'] = 4
print(json.dumps(d, ensure_ascii=False))
print(list(d.keys()))