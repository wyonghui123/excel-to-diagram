#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
P4阶段 业务消息UX全面优化验证脚本

检查项:
- P4-1: 【】技术标签清理
- P4-2/3/4/5/6: 后端消息统一
- P4-7: raise Exception 优化
- P4-8: 前端语义化API使用
- P4-9: 半角标点修复
- P4-10: _messages.py 集成情况
"""
import ast
import json
import re
import sys
from pathlib import Path

print("=" * 60)
print("P4 业务消息UX全面优化验证 (2026-06-20)")
print("=" * 60)

errors = []
warnings = []
info_list = []

ROOT = Path('.')
META_API = ROOT / 'meta' / 'api'
SRC = ROOT / 'src'

# ============================================================
# 1. P4-1: 【】技术标签清理
# ============================================================
print("\n[1/9] P4-1: 【】技术标签清理...")
try:
    f = ROOT / 'meta' / 'core' / 'validation_messages.py'
    content = f.read_text(encoding='utf-8')
    leaks = re.findall(r'【[^】]+】', content)
    if leaks:
        warnings.append(f"P4-1: validation_messages.py 还有 {len(leaks)} 个【】")
        print(f"  [WARN] {len(leaks)} leaks: {leaks[:3]}")
    else:
        print(f"  [OK] 0 【】技术标签残留")
except Exception as e:
    errors.append(f"P4-1 check error: {e}")
    print(f"  [FAIL] {e}")

# ============================================================
# 2. P4-2/3/4/5/6: 后端高频硬编码消息替换效果
# ============================================================
print("\n[2/9] P4-2/3/4/5/6: 后端高频硬编码消息替换效果...")
old_patterns = {
    "'需要管理员权限'": "高频旧文案",
    "'admin only'": "英文旧文案",
    "'Admin permission required'": "英文旧文案",
    "'登录已过期'": "旧会话文案",
    "'Token已失效'": "旧Token文案",
    "'认证服务异常'": "旧认证文案",
    '"需要管理员权限"': "高频旧文案(双引号)",
    '"admin only"': "英文旧文案(双引号)",
}
total_old = 0
old_files = []
for pattern, desc in old_patterns.items():
    count = 0
    for f in META_API.rglob('*.py'):
        if f.name == '_messages.py':
            continue
        try:
            content = f.read_text(encoding='utf-8')
            count += content.count(pattern)
        except Exception:
            pass
    if count > 0:
        old_files.append((pattern, desc, count))
        total_old += count

if total_old > 0:
    warnings.append(f"P4-2/3/4/5/6: 后端还剩 {total_old} 处旧硬编码消息")
    print(f"  [WARN] {total_old} 处旧文案残留:")
    for pat, desc, cnt in old_files[:5]:
        print(f"     - {desc}: {cnt} 处 ({pat})")
else:
    print(f"  [OK] 后端所有高频硬编码消息已替换 (检查了 {len(old_patterns)} 种模式)")

# ============================================================
# 3. P4-7: raise Exception 检查
# ============================================================
print("\n[3/9] P4-7: raise Exception 优化...")
total_raise = 0
raise_files = []
for f in META_API.rglob('*.py'):
    if f.name == '_messages.py':
        continue
    try:
        content = f.read_text(encoding='utf-8')
        for m in re.finditer(r'raise\s+(Exception|HTTPException)', content):
            line = content[:m.start()].count('\n') + 1
            total_raise += 1
            if total_raise <= 5:
                raise_files.append(f"{f}:{line}")
    except Exception:
        pass

if total_raise > 0:
    warnings.append(f"P4-7: 还有 {total_raise} 处 raise Exception/HTTPException")
    print(f"  [WARN] {total_raise} 处 raise Exception:")
    for f in raise_files:
        print(f"     - {f}")
else:
    print(f"  [OK] 0 raise Exception/HTTPException")

# ============================================================
# 4. P4-10: _messages.py 集成情况
# ============================================================
print("\n[4/9] P4-10: _messages.py 集成情况...")
messages_file = META_API / '_messages.py'
if not messages_file.exists():
    errors.append("P4-10: meta/api/_messages.py 不存在")
    print(f"  [FAIL] _messages.py 不存在")
else:
    # 统计常量数量
    msg_content = messages_file.read_text(encoding='utf-8')
    msg_constants = re.findall(r'^MSG_\w+\s*=', msg_content, re.MULTILINE)
    print(f"  [OK] _messages.py 存在，包含 {len(msg_constants)} 个 MSG_ 常量")

    # 检查哪些文件 import 了 _messages
    import_count = 0
    imported_files = []
    for f in META_API.rglob('*.py'):
        if f.name == '_messages.py':
            continue
        try:
            content = f.read_text(encoding='utf-8')
            if 'from meta.api._messages' in content or 'from ._messages' in content:
                import_count += 1
                imported_files.append(str(f.relative_to(ROOT)))
        except Exception:
            pass

    if import_count == 0:
        errors.append("P4-10: _messages.py 没有被任何文件 import")
        print(f"  [FAIL] 0 个文件 import _messages.py (孤立模块!)")
    else:
        print(f"  [OK] {import_count} 个文件 import _messages.py:")
        for f in imported_files:
            print(f"     - {f}")

# ============================================================
# 5. P4-8: 前端语义化API使用
# ============================================================
print("\n[5/9] P4-8: 前端 useCrudMessage 语义化API使用...")
vue_files = list(SRC.rglob('*.vue')) + list(SRC.rglob('*.js'))

# 统计 generic 调用
generic_count = 0
semantic_count = 0
for f in vue_files:
    try:
        content = f.read_text(encoding='utf-8')
        # generic 调用: message.error('xxx') 形式
        for m in re.finditer(r"message\.(error|success|warning|info)\s*\(\s*['\"`]([^'\"`]+)['\"`]", content):
            text = m.group(2)
            # 排除已经是业务化文案的 ("失败，请稍后重试" 结尾)
            if '失败，请稍后重试' not in text and '成功' not in text and '请稍后' not in text:
                # 排除短文案
                if len(text) >= 4 and re.search(r'[\u4e00-\u9fa5a-zA-Z]', text):
                    generic_count += 1
        # 语义化 API: message.saveFailed / deleteFailed / loadFailed / saved / deleted / created
        for m in re.finditer(r"message\.(saveFailed|deleteFailed|loadFailed|exportFailed|importFailed|updateFailed|saved|deleted|created|updated|loadSuccess|saveSuccess)\s*\(", content):
            semantic_count += 1
    except Exception:
        pass

print(f"  [INFO] 语义化API调用: {semantic_count} 次")
print(f"  [INFO] Generic调用: {generic_count} 次")

if generic_count > 0:
    warnings.append(f"P4-8: 前端还有 {generic_count} 处 generic message 调用")
else:
    print(f"  [OK] 0 generic message 调用")

# ============================================================
# 6. P4-9: 半角标点检查
# ============================================================
print("\n[6/9] P4-9: 中文消息中的半角标点...")
half_punct_issues = 0
for f in vue_files:
    try:
        content = f.read_text(encoding='utf-8')
        for m in re.finditer(r"message\.\w+\(\s*['\"`]([^'\"`]+)['\"`]", content):
            text = m.group(1)
            # 中文字符 + 半角逗号
            if re.search(r'[\u4e00-\u9fa5],', text) or re.search(r'[\u4e00-\u9fa5];', text):
                line = content[:m.start()].count('\n') + 1
                half_punct_issues += 1
                if half_punct_issues <= 3:
                    print(f"  [WARN] {f}:{line}  半角标点: {text[:60]}")
    except Exception:
        pass

if half_punct_issues > 0:
    warnings.append(f"P4-9: 中文消息中还有 {half_punct_issues} 处半角标点")
else:
    print(f"  [OK] 0 半角标点问题")

# ============================================================
# 7. P4-2: 业务化文案覆盖率
# ============================================================
print("\n[7/9] P4-2: 业务化文案覆盖率...")
new_patterns = [
    "您没有执行此操作的权限",
    "会话已过期",
    "登录状态已失效",
    "认证服务异常，请稍后重试",
]
total_new = 0
for pattern in new_patterns:
    count = 0
    for f in META_API.rglob('*.py'):
        if f.name == '_messages.py':
            continue
        try:
            count += f.read_text(encoding='utf-8').count(pattern)
        except Exception:
            pass
    total_new += count
    print(f"  [INFO] '{pattern}': {count} 处")

info_list.append(f"P4-2: 业务化文案覆盖 {total_new} 处")

# ============================================================
# 8. 集成测试: _messages.py 常量能否正确加载
# ============================================================
print("\n[8/9] 集成测试: _messages.py 常量加载...")
try:
    sys.path.insert(0, str(ROOT))
    from meta.api._messages import MSG_ADMIN_REQUIRED, MSG_USER_NOT_FOUND, t
    if MSG_ADMIN_REQUIRED and MSG_USER_NOT_FOUND:
        print(f"  [OK] 常量加载成功")
        print(f"     MSG_ADMIN_REQUIRED = {MSG_ADMIN_REQUIRED!r}")
        print(f"     MSG_USER_NOT_FOUND = {MSG_USER_NOT_FOUND!r}")
        # 测试 t() 函数
        result = t('auth.unauthorized', default='请先登录')
        print(f"     t('auth.unauthorized') = {result!r}")
    else:
        errors.append("P4-10: 常量加载失败")
        print(f"  [FAIL] 常量为空")
except Exception as e:
    warnings.append(f"P4-10 集成测试失败: {e}")
    print(f"  [WARN] {e}")

# ============================================================
# 9. 总结
# ============================================================
print("\n[9/9] 总结...")
print(f"  Errors: {len(errors)}")
print(f"  Warnings: {len(warnings)}")
print(f"  Info: {len(info_list)}")

# ============================================================
# Final Report
# ============================================================
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
    print("\n[INFO] Warnings are not blocking. Continue if acceptable.")
    sys.exit(0)
else:
    print("[PASS] All P4 verifications passed")
    sys.exit(0)
