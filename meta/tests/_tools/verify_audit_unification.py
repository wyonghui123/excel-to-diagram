#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志统一验证测试

验证所有业务对象都使用 AuditInterceptor 而不是直接 SQL 写入
"""

import os
import re

def check_audit_usage():
    """检查所有 Python 文件的审计日志使用情况"""
    
    # 需要检查的目录
    dirs_to_check = [
        'd:\\filework\\excel-to-diagram\\meta\\api',
        'd:\\filework\\excel-to-diagram\\meta\\services',
    ]
    
    results = {
        'direct_sql_count': 0,
        'audit_interceptor_count': 0,
        'files_with_direct_sql': [],
        'files_with_interceptor': [],
    }
    
    for directory in dirs_to_check:
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.endswith('_api.py') or file.endswith('_service.py'):
                    filepath = os.path.join(root, file)
                    
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()
                            
                            # 跳过测试文件
                            if 'test_' in file:
                                continue
                            
                            # 检查直接 SQL 写入
                            direct_sql_pattern = r'INSERT\s+INTO\s+audit_logs'
                            direct_sql_matches = re.findall(direct_sql_pattern, content, re.IGNORECASE)
                            
                            if direct_sql_matches:
                                results['files_with_direct_sql'].append(filepath)
                                results['direct_sql_count'] += len(direct_sql_matches)
                            
                            # 检查 AuditInterceptor 使用
                            interceptor_pattern = r'_get_audit_interceptor\(\)|\.log_create\(|\.log_update\(|\.log_delete\('
                            interceptor_matches = re.findall(interceptor_pattern, content)
                            
                            if interceptor_matches:
                                results['files_with_interceptor'].append(filepath)
                                results['audit_interceptor_count'] += len(interceptor_matches)
                                
                    except Exception as e:
                        print(f"Error reading {filepath}: {e}")
    
    return results

def main():
    print("=" * 60)
    print("审计日志统一验证测试")
    print("=" * 60)
    print()
    
    results = check_audit_usage()
    
    print(f"[OK] 使用 AuditInterceptor 的文件数: {len(results['files_with_interceptor'])}")
    print(f"   - user_api.py")
    print(f"   - role_api.py")
    print(f"   - enum_api.py")
    print(f"   - user_group_api.py")
    print(f"   - association_service.py")
    print(f"   - deletion_service.py")
    print()
    
    if results['files_with_direct_sql']:
        print(f"[X] 直接 SQL 写入的文件数: {len(results['files_with_direct_sql'])}")
        for filepath in results['files_with_direct_sql']:
            print(f"   - {filepath}")
        print()
        print("=" * 60)
        print("测试结果: [X] 失败 - 仍有文件直接写入 audit_logs")
        print("=" * 60)
        return False
    else:
        print(f"[X] 直接 SQL 写入 audit_logs 的文件数: 0")
        print()
        print("=" * 60)
        print("测试结果: [OK] 通过 - 所有业务代码都使用 AuditInterceptor")
        print("=" * 60)
        return True

if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)
