#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""P4 后端消息批量替换脚本"""
import re
import sys
from pathlib import Path

# 替换映射：源 -> 常量名
# 注意：保留单引号/双引号一致
REPLACE_MAP = {
    # 权限类 (使用 _messages.MSG_ADMIN_REQUIRED)
    "'需要管理员权限'": "'您没有执行此操作的权限，需要管理员权限'",
    '"需要管理员权限"': '"您没有执行此操作的权限，需要管理员权限"',
    "'admin only'": "'您没有执行此操作的权限，需要管理员权限'",
    '"admin only"': '"您没有执行此操作的权限，需要管理员权限"',
    "'Admin permission required'": "'您没有执行此操作的权限，需要管理员权限'",
    '"Admin permission required"': '"您没有执行此操作的权限，需要管理员权限"',
    "'Unauthorized'": "'请先登录后再操作'",
    '"Unauthorized"': '"请先登录后再操作"',
    "'Authentication required'": "'请先登录后再操作'",
    '"Authentication required"': '"请先登录后再操作"',
    "'Permission denied: {0}'": "'您没有执行此操作的权限'",
    # 认证类
    "'登录已过期'": "'会话已过期，请重新登录'",
    '"登录已过期"': '"会话已过期，请重新登录"',
    "'Token已失效'": "'登录状态已失效，请重新登录'",
    '"Token已失效"': '"登录状态已失效，请重新登录"',
    "'认证服务异常'": "'认证服务异常，请稍后重试'",
    '"认证服务异常"': '"认证服务异常，请稍后重试"',
    "'Forbidden'": "'您没有执行此操作的权限'",
    '"Forbidden"': '"您没有执行此操作的权限"',
    "'Not authenticated'": "'请先登录后再操作'",
    '"Not authenticated"': '"请先登录后再操作"',
    # 资源不存在
    "'用户不存在'": "'用户不存在，请检查后重试'",
    '"用户不存在"': '"用户不存在，请检查后重试"',
    "'角色不存在'": "'角色不存在，请检查后重试'",
    '"角色不存在"': '"角色不存在，请检查后重试"',
    "'Record not found'": "'记录不存在'",
    '"Record not found"': '"记录不存在"',
    "'Annotation not found'": "'标注不存在'",
    '"Annotation not found"': '"标注不存在"',
    "'Subscription not found'": "'订阅不存在'",
    '"Subscription not found"': '"订阅不存在"',
    "'审计日志不存在'": "'审计日志不存在'",
    '"审计日志不存在"': '"审计日志不存在"',
    # 请求校验
    "'请求体不能为空'": "'请求内容不能为空'",
    '"请求体不能为空"': '"请求内容不能为空"',
    "'Invalid id'": "'ID 无效'",
    '"Invalid id"': '"ID 无效"',
    "'target_id is required'": "'目标 ID 不能为空'",
    '"target_id is required"': '"目标 ID 不能为空"',
    "'target_type and target_id are required'": "'目标类型和目标 ID 不能为空'",
    '"target_type and target_id are required"': '"目标类型和目标 ID 不能为空"',
    "'content is required'": "'内容不能为空'",
    '"content is required"': '"内容不能为空"',
    "'target_id must be a valid numeric ID'": "'目标 ID 必须为有效数字'",
    '"target_id must be a valid numeric ID"': '"目标 ID 必须为有效数字"',
    "'resource_type and resource_id are required'": "'资源类型和资源 ID 不能为空'",
    '"resource_type and resource_id are required"': '"资源类型和资源 ID 不能为空"',
    "'user_id and bo_id are required'": "'用户 ID 和业务对象 ID 不能为空'",
    '"user_id and bo_id are required"': '"用户 ID 和业务对象 ID 不能为空"',
    "'steps 不能为空'": "'执行步骤不能为空'",
    '"steps 不能为空"': '"执行步骤不能为空"',
    # 系统角色
    "'系统角色不可修改'": "'系统内置角色不能修改'",
    '"系统角色不可修改"': '"系统内置角色不能修改"',
    # 用户/密码
    "'用户名和密码不能为空'": "'用户名和密码不能为空'",
    '"用户名和密码不能为空"': '"用户名和密码不能为空"',
    "'用户名不能为空'": "'用户名不能为空'",
    '"用户名不能为空"': '"用户名不能为空"',
    "'旧密码和新密码不能为空'": "'当前密码和新密码不能为空'",
    '"旧密码和新密码不能为空"': '"当前密码和新密码不能为空"',
    "'新密码长度不能少于6位'": "'新密码长度不能少于 6 位'",
    '"新密码长度不能少于6位"': '"新密码长度不能少于 6 位"',
    "'密码长度不能少于6位'": "'密码长度不能少于 6 位'",
    '"密码长度不能少于6位"': '"密码长度不能少于 6 位"',
    "'旧密码错误'": "'当前密码不正确'",
    '"旧密码错误"': '"当前密码不正确"',
    "'用户名已存在'": "'用户名已存在'",
    '"用户名已存在"': '"用户名已存在"',
    # 权限代码
    "'缺少权限: {0}'": "'缺少权限：{0}'",
    '"缺少权限: {0}"': '"缺少权限：{0}"',
    # 成功（业务化）
    "'登录成功'": "'登录成功'",
    '"登录成功"': '"登录成功"',
    "'登出成功'": "'已安全退出'",
    '"登出成功"': '"已安全退出"',
    "'密码修改成功'": "'密码修改成功'",
    '"密码修改成功"': '"密码修改成功"',
    "'用户更新成功'": "'用户信息已更新'",
    '"用户更新成功"': '"用户信息已更新"',
    "'用户删除成功'": "'用户已删除'",
    '"用户删除成功"': '"用户已删除"',
    "'个人信息更新成功'": "'个人信息已更新'",
    '"个人信息更新成功"': '"个人信息已更新"',
    "'权限规则添加成功'": "'权限规则已添加'",
    '"权限规则添加成功"': '"权限规则已添加"',
    "'模板下载成功'": "'模板下载成功'",
    '"模板下载成功"': '"模板下载成功"',
}

api_dir = Path('meta/api')
changed_files = []
total_changes = 0

for f in api_dir.rglob('*.py'):
    if f.name == '_messages.py':
        continue
    try:
        content = f.read_text(encoding='utf-8')
    except Exception:
        continue
    original = content
    file_changes = 0
    for old, new in REPLACE_MAP.items():
        if old in content:
            count = content.count(old)
            content = content.replace(old, new)
            file_changes += count
    if file_changes > 0:
        f.write_text(content, encoding='utf-8')
        changed_files.append((str(f), file_changes))
        total_changes += file_changes

print(f'\n[Total] {total_changes} changes in {len(changed_files)} files:')
for f, c in sorted(changed_files, key=lambda x: -x[1])[:20]:
    print(f'  {c:3d}  {f}')
if len(changed_files) > 20:
    print(f'  ... +{len(changed_files) - 20} more')
