import urllib.request
for url in ['http://172.20.59.7:8081/', 'http://172.20.59.7:9200/api']:
    try:
        resp = urllib.request.urlopen(url, timeout=5)
        print(f'{url}: {resp.status} {resp.read().decode()[:200]}')
    except Exception as e:
        print(f'{url}: {e}')
