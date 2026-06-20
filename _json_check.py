import json
d = {}
d['domain'] = 1
d['sub_domain'] = 2
d['service_module'] = 3
d['business_object'] = 4
d['relationship'] = 5
d['annotation'] = 6
with open(r'd:\filework\excel-to-diagram\_json_check_result.txt', 'w', encoding='utf-8') as f:
    f.write(f"memory order: {list(d.keys())}\n")
    f.write(f"json dumps: {json.dumps(d, ensure_ascii=False)}\n")