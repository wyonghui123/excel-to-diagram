# -*- coding: utf-8 -*-
"""[Debug] 看 registry.get_all() 返回什么"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meta.core.models import registry

all_oids = registry.get_all()
print(f'Total OIDs: {len(all_oids)}')
print(f'Sample: {all_oids[:20]}')
print()
# 看 product/version/domain 是否在
for need in ['product', 'version', 'domain', 'sub_domain', 'products', 'versions']:
    print(f'{need}: {"YES" if need in all_oids else "NO"}')
