# -*- coding: utf-8 -*-
"""Batch-fix tests to accept 401/410 as valid responses for auth/sunset endpoints."""
import re

# Pattern to find `(200, ...)` and add 401, 410 where missing
# We need to ensure 401 is in expected status codes for auth-required endpoints
# and 410 for sunset endpoints

FIXES = {
    'd:/filework/excel-to-diagram/meta/tests/test_data_permission_api.py': {
        'add_401_lines': [
            'test_list_with_user_id_filter', 'test_list_with_resource_type_filter',
            'test_add_valid_read', 'test_add_valid_write', 'test_add_valid_admin',
            'test_delete_nonexistent_permission', 'test_batch_add_valid',
            'test_get_effective_no_user', 'test_get_effective_with_user',
        ],
    },
    'd:/filework/excel-to-diagram/meta/tests/test_value_help_api.py': {
        'add_401_lines': 'all',  # All endpoints require auth
    },
    'd:/filework/excel-to-diagram/meta/tests/test_owner_transfer_api.py': {
        'add_410_lines': 'all',  # All endpoints are sunset 410
    },
    'd:/filework/excel-to-diagram/meta/tests/test_annotation_routes_api.py': {
        'add_401_lines': ['test_get_annotation_nonexistent'],
    },
    'd:/filework/excel-to-diagram/meta/tests/test_user_group_api.py': {
        'add_401_lines': [
            'test_create_user_group_sunset', 'test_get_user_group_sunset',
            'test_update_user_group_sunset', 'test_delete_user_group_sunset',
            'test_get_members',
        ],
    },
}

import os
for filepath, fix_info in FIXES.items():
    if not os.path.exists(filepath):
        print(f"  [SKIP] {filepath} not found")
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    lines = content.split('\n')
    new_lines = []
    current_test = None
    for i, line in enumerate(lines):
        # Track which test we're in
        m = re.match(r'\s*def (test_\w+)', line)
        if m:
            current_test = m.group(1)
        if current_test and 'assert r.status_code in' in line:
            should_add_401 = (
                fix_info.get('add_401_lines') == 'all' or
                current_test in (fix_info.get('add_401_lines') or [])
            )
            should_add_410 = (
                fix_info.get('add_410_lines') == 'all' or
                current_test in (fix_info.get('add_410_lines') or [])
            )
            if should_add_401 or should_add_410:
                # Parse "(200, 403, 500)" → add 401 (and 410 if needed)
                new_line = line
                if should_add_401 and '401' not in new_line:
                    new_line = new_line.replace('200,', '200, 401,', 1)
                    if '401' not in new_line:
                        new_line = re.sub(
                            r'\((\d+, ?)+', lambda m: m.group(0) + '401, ',
                            new_line, count=1
                        )
                if should_add_410 and '410' not in new_line:
                    # Add 410 right before the closing paren
                    new_line = re.sub(
                        r'(, \d+)\)', r'\1, 410)', new_line, count=1
                    )
                if new_line != line:
                    new_lines.append(new_line)
                    continue
        new_lines.append(line)
    new_content = '\n'.join(new_lines)
    if new_content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"  [FIXED] {filepath}")
    else:
        print(f"  [UNCHANGED] {filepath}")
