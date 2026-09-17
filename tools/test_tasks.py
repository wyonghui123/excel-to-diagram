import urllib.request,json,hashlib,time
h=int(time.time())//3600
t=hashlib.sha256(('v007.61-ops:'+str(h)).encode()).hexdigest()[:16]
resp=urllib.request.urlopen('http://172.20.59.7:9202/api/tasks?token='+t,timeout=10)
data=json.loads(resp.read().decode())
print('Total tasks:',data['count'])
for k,v in sorted(data['tasks'].items()):
    print(f"  {k}: {v['desc']} [{v['interval_human']}] exit={v['last_exit']}")
