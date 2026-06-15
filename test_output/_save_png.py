import re, base64, json, os
src_dir = r'C:\Users\ADMINI~1\AppData\Local\Temp\trae\toolcall-output'
# 找最新包含 "screenshot" 的文件
files = sorted([os.path.join(src_dir, f) for f in os.listdir(src_dir) if f.endswith('.txt')], key=os.path.getmtime, reverse=True)
print(f'found {len(files)} files')
for f in files[:3]:
    print(f, os.path.getmtime(f))
# 用最新的
latest = files[0]
with open(latest, 'r', encoding='utf-8', errors='ignore') as fp:
    txt = fp.read()
# 找所有 screenshot (考虑 JSON-in-string 转义)
ms = re.findall(r'\\"screenshot\\":\s*\\"([^\\"]+)\\"', txt)
print('found', len(ms), 'screenshots in', latest)
if ms:
    b64 = ms[0]
    out_path = r'd:\filework\excel-to-diagram\test_output\auto_check_bug_repro.jpg'
    with open(out_path, 'wb') as out:
        out.write(base64.b64decode(b64))
    print('saved to', out_path, 'size=', os.path.getsize(out_path))
