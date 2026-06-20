import requests
import json

# Login
s = requests.Session()
r = s.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
print('Login:', r.status_code)
print('Cookies:', dict(s.cookies))

# Get import result
import time
with open(r'D:\download\export_2026-06-18.xlsx', 'rb') as f:
    files = {'file': f}
    r = s.post('http://localhost:3010/api/v1/import/preview', files=files)
    print('Preview:', r.status_code)
    print('Preview results keys:', list(r.json().get('data', {}).get('sheets', [{}])[0].keys() if r.json().get('data', {}).get('sheets') else []))

# Start import
with open(r'D:\download\export_2026-06-18.xlsx', 'rb') as f:
    files = {'file': f}
    r = s.post('http://localhost:3010/api/v1/import/execute', files=files)
    print('Execute:', r.status_code)
    jid = r.json().get('data', {}).get('job_id')
    print('Job:', jid)

# Poll
for _ in range(20):
    time.sleep(2)
    r = s.get(f'http://localhost:3010/api/v1/import/status/{jid}')
    j = r.json().get('data', {})
    if j.get('status') == 'completed':
        results = j.get('result', {}).get('results', {})
        print('Results keys (Python dict order):', list(results.keys()))
        print('Results count:', len(results))
        with open(r'd:\filework\excel-to-diagram\_import_order_result.txt', 'w', encoding='utf-8') as outf:
            outf.write('API result.results keys (Python order): ' + str(list(results.keys())) + '\n')
        break