import urllib.request
import json

url = 'http://localhost:5000/api/v1/meta/reload'
req = urllib.request.Request(url, method='POST')
req.add_header('Content-Type', 'application/json')

try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        print('Reload result:', data)
except Exception as e:
    print('Error:', e)
