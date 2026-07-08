# -*- coding: utf-8 -*-
from meta.services.condition_evaluator import ConditionEvaluator

e = ConditionEvaluator()

assert e.evaluate('product_id = 1', {'product_id': 1}) == True
assert e.evaluate('product_id = 1', {'product_id': 2}) == False
assert e.evaluate('product_id IN (1, 2, 3)', {'product_id': 2}) == True
assert e.evaluate("product_id IN (1, 2, 3) AND domain_type = 'CORE'", {'product_id': 1, 'domain_type': 'CORE'}) == True
assert e.evaluate('id = 5', {'id': 5}) == True
assert e.evaluate('id = 5', {'id': 6}) == False

field_range = '{"fields": [{"name": "product_id", "operator": "in", "values": [1, 2, 3]}]}'
assert e.evaluate(field_range, {'product_id': 2}) == True
assert e.evaluate(field_range, {'product_id': 5}) == False

result = e.resolve_template('created_by = :user_id', {'user_id': 5})
assert result == 'created_by = 5'

refs = e.detect_instance_references('domain_id = 5 AND product_id = 1')
assert len(refs) == 2

assert e._validate_predicate('product_id = 1') == True
assert e._validate_predicate('DROP TABLE users') == False
assert e._validate_predicate('1=1; DELETE FROM users') == False

print('[OK] All ConditionEvaluator tests passed!')
