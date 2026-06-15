"""检查后端日志看 audit JOIN 是否执行"""
import requests

BASE = 'http://localhost:3010'
s = requests.Session()
s.get(f'{BASE}/api/v1/auth/dev-login?username=admin')

# 触发一次查询
r = s.get(f'{BASE}/api/v2/bo/user?page=1&page_size=5&ordering=-updated_at')
print(f'Status: {r.status_code}')
print(f'Success: {r.json().get("success")}')

# 读取后端日志
import os
log_paths = [
    r'd:\filework\excel-to-diagram\logs\app.log',
    r'd:\filework\excel-to-diagram\app.log',
]
for lp in log_paths:
    if os.path.exists(lp):
        print(f'\n=== 最后 50 行日志: {lp} ===')
        with open(lp, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-50:]
            for line in lines:
                if 'VirtualSort' in line or 'audit' in line.lower() or 'updated_at' in line:
                    print(line.rstrip())
        break
else:
    print('未找到日志文件')
