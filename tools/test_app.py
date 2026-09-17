import urllib.request
# Check which services are running and monitored
urls = [
    'http://172.20.59.7:9206/api/supervisor/services',
    'http://172.20.59.7:9206/api/supervisor/health',
    'http://172.20.59.7:8081/api/system/info',
]
for url in urls:
    try:
        resp = urllib.request.urlopen(url, timeout=10)
        print(f'{url}: {resp.status}')
        print(resp.read().decode()[:500])
        print('---')
    except Exception as e:
        print(f'{url}: {e}')
        print('---')
