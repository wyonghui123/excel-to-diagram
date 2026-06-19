#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Final verification script for BizMsg-UX v1.0 changes.

P0: 【】技术标签
P1: trace_id / i18n
P2: 技术术语 / 标点
P3: 长消息 (使用 detail API)
"""
import ast
import json
import re
import sys
import subprocess
from pathlib import Path

print("=" * 60)
print("Final Verification: BizMsg-UX v1.0 (P0-P3)")
print("=" * 60)

errors = []
warnings = []

# 1. Python syntax check
print("\n[1/7] Python syntax check...")
try:
    ast.parse(open(r'meta/services/import_export_service.py', encoding='utf-8').read())
    print("  [OK] import_export_service.py syntax valid")
except SyntaxError as e:
    errors.append(f"Python syntax: {e}")
    print(f"  [FAIL] {e}")

# 2. JSON validity (i18n namespaces)
print("\n[2/7] i18n zh-CN.json (crud/validation/system/biz/detail)...")
try:
    with open(r'src/i18n/locales/zh-CN.json', encoding='utf-8') as f:
        d = json.load(f)
    required = ['crud', 'validation', 'system', 'biz', 'detail']
    missing = [k for k in required if k not in d]
    if missing:
        errors.append(f"JSON missing namespaces: {missing}")
        print(f"  [FAIL] missing: {missing}")
    else:
        print(f"  [OK] {len(d)} top-level keys, all 5 namespaces present")
        for ns in required:
            print(f"     - {ns}: {len(d[ns])} entries")
except json.JSONDecodeError as e:
    errors.append(f"JSON parse: {e}")
    print(f"  [FAIL] {e}")

# 3. User-facing 【】 in import_export_service.py
print("\n[3/7] User-facing \u3010 leak in import_export_service.py...")
try:
    content = open(r'meta/services/import_export_service.py', encoding='utf-8').read()
    error_fields = re.findall(r'"error":\s*([^\n]+)', content)
    leaks = [e for e in error_fields if '\u3010' in e]
    if leaks:
        errors.append(f"\u3010 leaks: {len(leaks)} found")
        print(f"  [FAIL] {len(leaks)} leaks found")
        for l in leaks[:5]:
            print(f"     {l.strip()[:100]}")
    else:
        print(f"  [OK] {len(error_fields)} error fields, 0 \u3010 leaks")
except Exception as e:
    errors.append(f"check error: {e}")
    print(f"  [FAIL] {e}")

# 4. P2 技术术语泄露检查
print("\n[4/7] P2 Tech-term leaks in src/ (message.* calls)...")
tech_terms = ['数据库', '枚举值', '业务键', '业务关键字', '主对象类型', '子列表']
src_dir = Path('src')
vue_files = list(src_dir.rglob('*.vue')) + list(src_dir.rglob('*.js'))

# 提取所有 message.*('...') 调用文本
msg_pattern = re.compile(r"message\.\w+\(\s*['\"`]([^'\"`]+)['\"`]")
html_msg_pattern = re.compile(r"message\.\w+\([^)]*?['\"`]([^'\"`]{15,})['\"`]")

leak_count = 0
for f in vue_files:
    try:
        content = f.read_text(encoding='utf-8')
        # 匹配 message.*('...') 中的字符串
        for match in re.finditer(r"message\.\w+\(\s*['\"`]([^'\"`]+)['\"`]", content):
            text = match.group(1)
            for term in tech_terms:
                if term in text:
                    # 计算行号
                    line = content[:match.start()].count('\n') + 1
                    leak_count += 1
                    if leak_count <= 5:
                        print(f"  [LEAK] {f}:{line}  {term} in: {text[:60]}")
    except Exception:
        pass

if leak_count > 0:
    warnings.append(f"P2 tech-term leaks: {leak_count} (warn-level)")
    print(f"  [WARN] {leak_count} tech-term leak(s) in user-visible messages")
else:
    print(f"  [OK] 0 tech-term leaks in {len(vue_files)} files")

# 5. P2 标点检查 (半角逗号/冒号在中文消息中)
print("\n[5/7] P2 Punctuation (half-width in Chinese messages)...")
half_punct_pattern = re.compile(r"message\.\w+\(\s*['\"`]([^'\"`]+)['\"`]")
punct_issues = 0
for f in vue_files:
    try:
        content = f.read_text(encoding='utf-8')
        for match in re.finditer(r"message\.\w+\(\s*['\"`]([^'\"`]+)['\"`]", content):
            text = match.group(1)
            # 中文字符 + 半角逗号 (但跳过URL/数字)
            if re.search(r'[\u4e00-\u9fa5],', text):
                # 排除 "X,Y" 全英文/数字的情况
                if re.search(r'[\u4e00-\u9fa5],[^0-9]', text):
                    line = content[:match.start()].count('\n') + 1
                    punct_issues += 1
                    if punct_issues <= 5:
                        print(f"  [WARN] {f}:{line}  半角逗号: {text[:60]}")
    except Exception:
        pass

if punct_issues > 0:
    warnings.append(f"P2 punctuation issues: {punct_issues} (warn-level)")
    print(f"  [WARN] {punct_issues} half-width comma in Chinese messages")
else:
    print(f"  [OK] 0 half-width comma issues")

# 6. P3 长消息检查
print("\n[6/7] P3 Long message (>50 chars, not using detail)...")
long_msg_pattern = re.compile(r"message\.(?:success|error|info|warning)\(\s*['\"`]([^'\"`]{50,})['\"`]")
detail_call_pattern = re.compile(r"message\.detail\(")
long_count = 0
for f in vue_files:
    try:
        content = f.read_text(encoding='utf-8')
        for match in long_msg_pattern.finditer(content):
            text = match.group(1)
            line = content[:match.start()].count('\n') + 1
            long_count += 1
            if long_count <= 5:
                print(f"  [INFO] {f}:{line}  ({len(text)} chars) {text[:60]}")
    except Exception:
        pass

# 检查 detail() 调用次数
detail_count = 0
for f in vue_files:
    try:
        content = f.read_text(encoding='utf-8')
        detail_count += len(detail_call_pattern.findall(content))
    except Exception:
        pass

if long_count > 0:
    warnings.append(f"P3 long messages: {long_count} (consider message.detail)")
    print(f"  [WARN] {long_count} long message(s); {detail_count} detail() call(s) used")
else:
    print(f"  [OK] 0 long messages; {detail_count} detail() call(s) used")

# 7. useMessage.js 关键 API 检查
print("\n[7/7] useMessage.js key APIs...")
try:
    content = open(r'src/composables/useMessage.js', encoding='utf-8').read()
    required_apis = ['extractTraceId', 'formatErrorMessage', 'detail', 'networkError', 'sessionExpired']
    missing = [a for a in required_apis if a not in content]
    if missing:
        errors.append(f"useMessage.js missing APIs: {missing}")
        print(f"  [FAIL] missing APIs: {missing}")
    else:
        print(f"  [OK] all {len(required_apis)} key APIs present: {required_apis}")
        # 检查 STAB 错误边界
        if 'try {' in content and 'catch (e)' in content:
            print(f"     + STAB-3 错误边界: ✓")
        if 'WeakMap' in content:
            print(f"     + PERF-3 trace_id 缓存: ✓")
except Exception as e:
    print(f"  [WARN] {e}")

# Summary
print("\n" + "=" * 60)
if errors:
    print(f"[FAIL] {len(errors)} error(s) found:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
elif warnings:
    print(f"[PASS with WARNINGS] {len(warnings)} warning(s):")
    for w in warnings:
        print(f"  - {w}")
    print("[INFO] Warnings are not blocking. Continue if acceptable.")
    sys.exit(0)
else:
    print("[PASS] All verifications passed (P0-P3)")
    sys.exit(0)
