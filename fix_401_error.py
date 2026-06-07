#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
401 认证错误诊断和修复脚本

解决前端访问 API 时遇到的 401 UNAUTHORIZED 错误
"""

import os
import sys
import sqlite3
from datetime import datetime

def diagnose_401_error():
    """诊断 401 错误"""
    print("=" * 60)
    print("401 认证错误诊断")
    print("=" * 60)
    
    # 1. 检查数据库
    db_path = os.path.join(os.path.dirname(__file__), 'meta', 'architecture.db')
    if not os.path.exists(db_path):
        print("[X] 数据库文件不存在")
        return False
    
    print(f"[OK] 数据库文件存在: {db_path}")
    
    # 2. 检查用户表
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT id, username, display_name, status FROM users LIMIT 5")
        users = cursor.fetchall()
        if users:
            print(f"[OK] 找到 {len(users)} 个用户:")
            for user in users:
                print(f"   - ID: {user[0]}, 用户名: {user[1]}, 显示名: {user[2]}, 状态: {user[3]}")
        else:
            print("[X] 没有找到用户，需要初始化用户数据")
            return False
    except Exception as e:
        print(f"[X] 查询用户失败: {e}")
        return False
    finally:
        conn.close()
    
    # 3. 检查 .env 文件
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        print(f"[OK] .env 文件存在: {env_file}")
        with open(env_file, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'JWT_SECRET_KEY' in content:
                print("[OK] JWT_SECRET_KEY 已配置")
            else:
                print("[WARNING]  JWT_SECRET_KEY 未配置，将使用开发密钥")
    else:
        print("[WARNING]  .env 文件不存在，将使用开发密钥")
    
    # 4. 检查后端服务
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('127.0.0.1', 5000))
    sock.close()
    
    if result == 0:
        print("[OK] 后端服务正在运行 (端口 5000)")
    else:
        print("[X] 后端服务未运行，请先启动服务:")
        print("   python meta/server.py")
        return False
    
    return True


def create_test_token():
    """创建测试 Token"""
    print("\n" + "=" * 60)
    print("创建测试 Token")
    print("=" * 60)
    
    from meta.services.token_service import TokenService
    from meta.services.auth_provider import LocalAuthProvider
    from meta.core.datasource import get_data_source
    
    # 获取数据源
    db_path = os.path.join(os.path.dirname(__file__), 'meta', 'architecture.db')
    data_source = get_data_source('sqlite', database=db_path)
    
    # 获取管理员用户
    auth_provider = LocalAuthProvider(data_source)
    user_info = auth_provider.authenticate({'username': 'admin', 'password': 'admin123'})
    
    if not user_info:
        print("[X] 管理员用户不存在或密码错误")
        print("   请先创建管理员用户:")
        print("   python meta/scripts/init_auth.py")
        return None
    
    # 创建 Token
    token, expires_at = TokenService.create_token(user_info)
    
    print(f"[OK] Token 创建成功!")
    print(f"   用户: {user_info.username}")
    print(f"   过期时间: {expires_at}")
    print(f"\n[DECORATIVE] Token (复制到浏览器控制台):")
    print(f"   localStorage.setItem('auth_token', '{token}');")
    print(f"   localStorage.setItem('auth_user', '{user_info.to_dict()}');")
    
    return token


def test_api_with_token(token):
    """使用 Token 测试 API"""
    print("\n" + "=" * 60)
    print("测试 API 访问")
    print("=" * 60)
    
    import requests
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json'
    }
    
    # 测试用户列表 API
    try:
        response = requests.get('http://127.0.0.1:5000/api/v1/users', headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"[OK] API 访问成功!")
            print(f"   返回 {len(data.get('data', []))} 个用户")
            return True
        elif response.status_code == 401:
            print(f"[X] API 访问失败: 401 UNAUTHORIZED")
            print(f"   响应: {response.text}")
            return False
        else:
            print(f"[WARNING]  API 返回状态码: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
    except Exception as e:
        print(f"[X] API 请求失败: {e}")
        return False


def fix_401_issue():
    """修复 401 问题"""
    print("\n" + "=" * 60)
    print("修复 401 问题")
    print("=" * 60)
    
    # 1. 诊断问题
    if not diagnose_401_error():
        print("\n[X] 诊断失败，请先解决上述问题")
        return
    
    # 2. 创建测试 Token
    token = create_test_token()
    if not token:
        print("\n[X] Token 创建失败")
        return
    
    # 3. 测试 API
    if test_api_with_token(token):
        print("\n[OK] 问题已解决!")
        print("\n[DECORATIVE] 请在前端执行以下操作:")
        print("   1. 打开浏览器开发者工具 (F12)")
        print("   2. 切换到 Console 标签")
        print("   3. 执行上面生成的 localStorage 命令")
        print("   4. 刷新页面")
    else:
        print("\n[X] API 测试失败，请检查后端日志")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='401 认证错误诊断和修复')
    parser.add_argument('--diagnose', action='store_true', help='仅诊断问题')
    parser.add_argument('--create-token', action='store_true', help='创建测试 Token')
    parser.add_argument('--test-api', action='store_true', help='测试 API 访问')
    
    args = parser.parse_args()
    
    if args.diagnose:
        diagnose_401_error()
    elif args.create_token:
        create_test_token()
    elif args.test_api:
        from meta.services.token_service import TokenService
        token = create_test_token()
        if token:
            test_api_with_token(token)
    else:
        fix_401_issue()


if __name__ == '__main__':
    main()
