import socket, time
ports = [3004, 3005, 3010, 3011]
for p in ports:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(('127.0.0.1', p))
        print(f"PORT {p}: UP")
        s.close()
    except Exception as e:
        print(f"PORT {p}: DOWN ({e.__class__.__name__})")
        s.close()