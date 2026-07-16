import zipfile
v = zipfile.ZipFile('deploy_bundle/deploy-v20260706_021.zip')
names = v.namelist()
tel = [n for n in names if n.startswith('telemetry/')]
mcp = [n for n in names if n.startswith('mcp/')]
print(f'total: {len(names)}')
print(f'telemetry: {len(tel)}')
print(f'mcp: {len(mcp)}')
print(f'cache_manager V007.21 fix (0 async, 3 sync):')
import re
c = v.read('meta/core/enums/cache_manager.py').decode()
nc = '\n'.join(l for l in c.split('\n') if not l.lstrip().startswith('#'))
print(f'  async with self._lock: {len(re.findall(r"async with self._lock", nc))}')
print(f'  with self._lock::     {len(re.findall(r"with self._lock:", nc, re.MULTILINE))}')
print(f'busy_timeout: {"busy_timeout = 30000" in v.read("meta/core/sql_connection_pool.py").decode()}')
print(f'skip_audit: {v.read("meta/services/import_export_service.py").decode().count("skip_audit=True")}')
