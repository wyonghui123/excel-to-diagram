import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
s.connect(('127.0.0.1', 3010))
s.send(b'GET /api/v1/auth/dev-login?username=admin HTTP/1.0\r\nHost: localhost:3010\r\n\r\n')
data = b''
while True:
    chunk = s.recv(4096)
    if not chunk: break
    data += chunk
print(data.decode('utf-8', errors='replace')[:2000])
s.close()