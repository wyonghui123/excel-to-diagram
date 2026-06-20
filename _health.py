import urllib.request
try:
    r = urllib.request.urlopen('http://localhost:3010/api/v1/health', timeout=3)
    print('Backend OK:', r.status, r.read().decode())
except Exception as e:
    print('Backend error:', e)

with open(r'd:\filework\excel-to-diagram\_backend_status.txt', 'w', encoding='utf-8') as f:
    try:
        r = urllib.request.urlopen('http://localhost:3010/api/v1/health', timeout=3)
        f.write('Backend OK: ' + str(r.status) + ' ' + r.read().decode() + '\n')
    except Exception as e:
        f.write('Backend error: ' + str(e) + '\n')