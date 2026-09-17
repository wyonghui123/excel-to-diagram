import urllib.request,json,hashlib,time
h=int(time.time())//3600
for s in ['v007.35-infra']:
    for off in [-1, 0, 1]:
        h2 = h - off
        t = hashlib.sha256((s+':'+str(h2)).encode()).hexdigest()[:16]
        url = 'http://172.20.59.7:9101/api/token?test='+t
        try:
            resp = urllib.request.urlopen(url, timeout=5)
            r = resp.read().decode()
            print(f'{s} h={h2}: {r[:200]}')
        except Exception as e:
            print(f'{s} h={h2}: {e}')
