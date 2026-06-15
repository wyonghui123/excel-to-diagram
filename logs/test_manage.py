import sys, os
os.chdir('d:/filework/excel-to-diagram')
sys.path.insert(0, '.')
from meta.database import get_default_data_source
from meta.services.manage_service import ManageService
from meta.core import registry

# 看 meta_object.user_group 的 deletion_policy
obj = registry.get('user_group')
print('user_group meta_object:')
print('  has deletion_policy:', hasattr(obj, 'deletion_policy'))
dp = getattr(obj, 'deletion_policy', None)
if dp:
    print('  policy type:', type(dp))
    if isinstance(dp, dict):
        print('  restrict_on:', dp.get('restrict_on', 'MISSING'))
    else:
        print('  restrict_on:', getattr(dp, 'restrict_on', 'MISSING'))

# 直接调 manage_service.batch_delete('user_group', [482])
ds = get_default_data_source()
# 用 bo_framework 实例
from meta.core.bo_framework import BOFramework
bo = BOFramework(ds)
ms = ManageService(ds)
ms.set_audit_user(1, 'admin', '127.0.0.1', 'test')

print()
print('=== batch_delete(user_group, [482]) ===')
result = ms.batch_delete('user_group', [482], force=False)
print('success:', result.success_count, 'failed:', result.failed_count)
print('errors:', result.errors)
print('results:')
for r in result.results:
    print('  success:', r.success, 'message:', r.message, 'error:', r.error)
