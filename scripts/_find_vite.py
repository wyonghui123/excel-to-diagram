import socket
for p in [3004, 3005, 3006, 3007, 3008]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(('127.0.0.1', p))
        # peek first bytes to identify
        s.send(b'GET / HTTP/1.0\r\n\r\n')
        data = s.recv(256).decode(errors='replace')
        is_vite = 'vite' in data.lower() or 'archworkspace' in data.lower()
        print(f"PORT {p}: UP  vite={is_vite}")
        s.close()
    except Exception as e:
        print(f"PORT {p}: DOWN")
        s.close()