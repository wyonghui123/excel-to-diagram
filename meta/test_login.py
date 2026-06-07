import requests

url = "http://localhost:3005/api/v1/auth/login"
data = {"username": "admin", "password": "admin123"}

try:
    print(f"Connecting to {url}...")
    response = requests.post(url, json=data, timeout=30)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
