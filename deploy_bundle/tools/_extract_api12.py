import zipfile, re
z = zipfile.ZipFile(r'd:\filework\release-prep-worktree\deploy_bundle\deploy-v20260706_021.zip')
content = z.read('frontend_dist_files/assets/index-48IrQ6VL.js').decode('utf-8', errors='ignore')

# 找 const gt = ... 或 let gt = ...
print('=== gt = ... ===')
for m in re.finditer(r'\bconst\s+gt\s*=', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+400]}')
    print()

# 找 function gt(
print()
print('=== function gt( ===')
for m in re.finditer(r'function\s+gt\s*\(', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+400]}')
    print()

# 找 gt: function
print()
print('=== gt: function ===')
for m in re.finditer(r'\bgt\s*:\s*function', content):
    pos = m.start()
    print(f'pos {pos}: {content[max(0,pos-30):pos+400]}')
    print()
