"""测试 view_config_service"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from meta.services.view_config_service import view_config_service

# 清除缓存
view_config_service._cache.clear()

# 测试 get_or_build_view_config
config = view_config_service.get_or_build_view_config('user', 'table')
if config and config.list:
    # 检查 columns
    for col in config.list.columns:
        if col.key == 'status':
            print('status 列 filter_type:', repr(col.filter_type))

    # 检查 filters
    if config.list.filters:
        for f in config.list.filters:
            if f.get('field') == 'status':
                print('status filter type:', repr(f.get('type')))
                print('status filter value_help:', f.get('value_help'))
else:
    print('config 或 config.list 为空')
