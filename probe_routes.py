from meta.server import create_app
app = create_app()
print("=== /api/v1/user-groups* routes ===")
for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
    if 'user-groups' in rule.rule or 'user_group' in rule.rule:
        methods = sorted(rule.methods - {'HEAD', 'OPTIONS'})
        print(f"  {','.join(methods):10s}  {rule.rule:55s}  ->  {rule.endpoint}")
