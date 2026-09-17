"""Batch upload files to yonaa deployment directories"""
import http.client
import json
import hashlib
import time
import os
import sys
import glob

HOST = '172.20.59.7'
PORT = 9201
SECRET = 'v007.52-core-write'

def get_token():
    h = int(time.time()) // 3600
    return hashlib.sha256(f"{SECRET}:{h}".encode()).hexdigest()[:16]

def upload_file(local_path, remote_name, base_dir):
    token = get_token()
    with open(local_path, 'rb') as f:
        content = f.read()

    boundary = 'BatchUploadBoundary789'
    part_header = (
        '--' + boundary + '\r\n'
        'Content-Disposition: form-data; name="file"; filename="' + remote_name + '"\r\n'
        'Content-Type: application/octet-stream\r\n\r\n'
    )
    body = part_header.encode('latin-1') + content + ('\r\n--' + boundary + '--\r\n').encode('latin-1')

    conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
    url = f'/api/upload_multi?base_dir={base_dir}&token={token}'
    conn.request('POST', url, body=body,
                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()
    return data

def upload_batch(files, base_dir):
    """Upload multiple files, each with its own filename"""
    token = get_token()
    boundary = 'MultiBatchBoundary999'
    parts = []
    for local_path, remote_name in files:
        with open(local_path, 'rb') as f:
            content = f.read()
        parts.append((remote_name, content))

    # Build multipart body with all parts
    body_parts = []
    for remote_name, content in parts:
        part_header = (
            '--' + boundary + '\r\n'
            'Content-Disposition: form-data; name="file"; filename="' + remote_name + '"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n'
        )
        body_parts.append(part_header.encode('latin-1'))
        body_parts.append(content)
        body_parts.append('\r\n'.encode('latin-1'))
    body_parts.append(('--' + boundary + '--\r\n').encode('latin-1'))
    body = b''.join(body_parts)

    conn = http.client.HTTPConnection(HOST, PORT, timeout=60)
    url = f'/api/upload_multi?base_dir={base_dir}&token={token}'
    conn.request('POST', url, body=body,
                 headers={'Content-Type': f'multipart/form-data; boundary={boundary}'})
    resp = conn.getresponse()
    data = json.loads(resp.read().decode())
    conn.close()
    return data

def main():
    project_root = r'd:\filework\worktrees/release-prep'
    ok_total = 0
    fail_total = 0

    # === Backend: 3 interceptor files ===
    print("\n=== Uploading Backend Interceptors ===")
    interceptor_dir = '/opt/app/deployments/meta/core/interceptors'
    interceptor_files = [
        'write_scope_interceptor.py',
        'data_permission_interceptor.py',
        'permission_interceptor.py',
    ]
    for fname in interceptor_files:
        local = os.path.join(project_root, 'meta', 'core', 'interceptors', fname)
        result = upload_file(local, fname, interceptor_dir)
        ok = result.get('ok', 0)
        fail = result.get('fail', 0)
        ok_total += ok
        fail_total += fail
        status = 'OK' if ok > 0 else 'FAIL'
        print(f"  {fname}: {status}")

    # === Backend: init_menu_permissions.py ===
    print("\n=== Uploading Backend Scripts ===")
    script_dir = '/opt/app/deployments/meta/scripts'
    local = os.path.join(project_root, 'meta', 'scripts', 'init_menu_permissions.py')
    result = upload_file(local, 'init_menu_permissions.py', script_dir)
    ok_total += result.get('ok', 0)
    fail_total += result.get('fail', 0)
    print(f"  init_menu_permissions.py: {'OK' if result.get('ok',0) > 0 else 'FAIL'}")

    # === Frontend: dist/assets/* (batch multiple files per request) ===
    print("\n=== Uploading Frontend Assets ===")
    assets_dir = '/opt/app/deployments/frontend_dist_files/assets'
    dist_assets = os.path.join(project_root, 'dist', 'assets')
    asset_files = sorted(os.listdir(dist_assets))
    print(f"  Total asset files: {len(asset_files)}")
    # Batch in groups of 10 to avoid oversized requests
    batch_size = 10
    for i in range(0, len(asset_files), batch_size):
        batch = asset_files[i:i+batch_size]
        files_batch = [(os.path.join(dist_assets, f), f) for f in batch if os.path.isfile(os.path.join(dist_assets, f))]
        if files_batch:
            result = upload_batch(files_batch, assets_dir)
            ok_total += result.get('ok', 0)
            fail_total += result.get('fail', 0)
    print(f"  Assets: cumulative ok={ok_total} fail={fail_total}")

    # === Frontend: dist/index.html + other root files ===
    print("\n=== Uploading Frontend Root Files ===")
    root_dir = '/opt/app/deployments/frontend_dist_files'
    dist_root = os.path.join(project_root, 'dist')
    for item in os.listdir(dist_root):
        local = os.path.join(dist_root, item)
        if os.path.isfile(local):
            result = upload_file(local, item, root_dir)
            ok_total += result.get('ok', 0)
            fail_total += result.get('fail', 0)
            print(f"  {item}: {'OK' if result.get('ok',0) > 0 else 'FAIL'}")

    # === Frontend: dist/docs/ and other subdirectories ===
    for sub in ['docs']:
        sub_remote = f'/opt/app/deployments/frontend_dist_files/{sub}'
        sub_local = os.path.join(dist_root, sub)
        if os.path.isdir(sub_local):
            print(f"\n=== Uploading dist/{sub}/ ===")
            count = 0
            for root, dirs, files in os.walk(sub_local):
                rel = os.path.relpath(root, dist_root)
                remote_dir = f'/opt/app/deployments/frontend_dist_files/{rel.replace(os.sep, "/")}'
                for fname in files:
                    local = os.path.join(root, fname)
                    result = upload_file(local, fname, remote_dir)
                    ok_total += result.get('ok', 0)
                    fail_total += result.get('fail', 0)
                    count += 1
            print(f"  Uploaded {count} files")

    print(f"\n=== SUMMARY === ok={ok_total} fail={fail_total} ===")

if __name__ == '__main__':
    main()
