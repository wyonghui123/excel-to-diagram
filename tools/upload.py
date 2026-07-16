"""Upload a file to yonaa via observability upload_multi endpoint"""
import http.client, json, hashlib, time, sys, os

HOST = '172.20.59.7'
PORT = 9201
SECRET = 'v007.52-core-write'

def get_token():
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{SECRET}:{h}".encode()).hexdigest()[:16]

def upload_file(local_path, remote_name, base_dir="/tmp"):
    token = get_token()
    with open(local_path, 'rb') as f:
        content = f.read()

    boundary = 'PythonUploadBoundary123456'
    part_header = (
        '--' + boundary + '\r\n'
        'Content-Disposition: form-data; name="file"; filename="' + remote_name + '"\r\n'
        'Content-Type: application/octet-stream\r\n'
        '\r\n'
    )
    body = part_header.encode('utf-8') + content + ('\r\n--' + boundary + '--\r\n').encode('utf-8')

    conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
    conn.request('POST', f'/api/upload_multi?base_dir={base_dir}&token={token}',
                 body=body,
                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()
    return data

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python upload.py <local_file> [remote_name] [base_dir]")
        sys.exit(1)
    local_path = sys.argv[1]
    remote_name = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(local_path)
    base_dir = sys.argv[3] if len(sys.argv) > 3 else '/tmp'
    if not os.path.exists(local_path):
        print(f"File not found: {local_path}")
        sys.exit(1)
    result = upload_file(local_path, remote_name, base_dir)
    print(json.dumps(result, indent=2, ensure_ascii=False))
