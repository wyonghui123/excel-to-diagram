import json
# Test json.dumps behavior with Flask
d = {}
d['domain'] = 1
d['sub_domain'] = 2
d['service_module'] = 3
d['business_object'] = 4
d['relationship'] = 5
d['annotation'] = 6

# Default behavior
result1 = json.dumps(d, ensure_ascii=False)
print(f"Test 1 (no sort_keys): {result1}")

# sort_keys=True (Flask jsonify default)
result2 = json.dumps(d, ensure_ascii=False, sort_keys=True)
print(f"Test 2 (sort_keys=True): {result2}")

# JSONResponse default
try:
    from flask import jsonify
    result3 = jsonify(d)
    print(f"Test 3 (Flask jsonify): {result3.get_data(as_text=True)}")
except ImportError:
    print("Flask not installed")