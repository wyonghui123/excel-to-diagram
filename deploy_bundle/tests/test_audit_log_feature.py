#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计日志功能自动化测试
"""

import unittest
import requests
import json
import time
import os
from datetime import datetime, timedelta

BASE_URL = os.environ.get('TEST_API_URL', 'http://127.0.0.1:3010')  # v3.18 P1: 修复端口不一致 (5000 → 3010 + env var)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'admin123'


class TestAuditLogAPI(unittest.TestCase):
    """审计日志API测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试前登录获取token"""
        response = requests.post(f'{BASE_URL}/api/v1/auth/login', json={
            'username': ADMIN_USERNAME,
            'password': ADMIN_PASSWORD
        })
        data = response.json()
        cls.token = data.get('data', {}).get('token')
        cls.headers = {'Authorization': f'Bearer {cls.token}'}
        
        if not cls.token:
            raise Exception(f"登录失败: {data}")
    
    def test_01_get_audit_logs(self):
        """测试查询审计日志列表"""
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/logs',
            headers=self.headers,
            params={'page': 1, 'page_size': 20}
        )
        data = response.json()
        
        self.assertTrue(data.get('success'), f"查询失败: {data.get('message')}")
        self.assertIn('data', data)
        self.assertIn('total', data)
        self.assertIn('page', data)
        self.assertIn('page_size', data)
        print(f"[DECORATIVE] 查询审计日志列表成功，共 {data.get('total')} 条记录")
    
    def test_02_filter_by_action(self):
        """测试按操作类型过滤"""
        for action in ['CREATE', 'UPDATE', 'DELETE']:
            response = requests.get(
                f'{BASE_URL}/api/v1/audit/logs',
                headers=self.headers,
                params={'action': action, 'page': 1, 'page_size': 10}
            )
            data = response.json()
            
            self.assertTrue(data.get('success'))
            for log in data.get('data', []):
                self.assertEqual(log.get('action'), action)
            print(f"[DECORATIVE] 按操作类型 '{action}' 过滤成功")
    
    def test_03_filter_by_object_type(self):
        """测试按对象类型过滤"""
        for object_type in ['user', 'role', 'user_group']:
            response = requests.get(
                f'{BASE_URL}/api/v1/audit/logs',
                headers=self.headers,
                params={'object_type': object_type, 'page': 1, 'page_size': 10}
            )
            data = response.json()
            
            self.assertTrue(data.get('success'))
            print(f"[DECORATIVE] 按对象类型 '{object_type}' 过滤成功，共 {data.get('total')} 条")
    
    def test_04_filter_by_user_name(self):
        """测试按用户名搜索"""
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/logs',
            headers=self.headers,
            params={'user_name': 'admin', 'page': 1, 'page_size': 10}
        )
        data = response.json()
        
        self.assertTrue(data.get('success'))
        print(f"[DECORATIVE] 按用户名搜索成功，共 {data.get('total')} 条")
    
    def test_05_filter_by_date_range(self):
        """测试按时间范围过滤"""
        today = datetime.now().strftime('%Y-%m-%d')
        week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/logs',
            headers=self.headers,
            params={
                'start_date': week_ago,
                'end_date': today,
                'page': 1,
                'page_size': 20
            }
        )
        data = response.json()
        
        self.assertTrue(data.get('success'))
        self.assertGreater(data.get('total'), 0)
        print(f"[DECORATIVE] 按时间范围过滤成功，共 {data.get('total')} 条")
    
    def test_06_sort_by_created_at(self):
        """测试按时间排序"""
        for direction in ['desc', 'asc']:
            response = requests.get(
                f'{BASE_URL}/api/v1/audit/logs',
                headers=self.headers,
                params={
                    'sort_field': 'created_at',
                    'sort_direction': direction,
                    'page': 1,
                    'page_size': 5
                }
            )
            data = response.json()
            
            self.assertTrue(data.get('success'))
            logs = data.get('data', [])
            
            if len(logs) > 1:
                for i in range(len(logs) - 1):
                    if direction == 'desc':
                        self.assertGreaterEqual(
                            logs[i].get('created_at', ''),
                            logs[i+1].get('created_at', ''),
                            "降序排列验证失败"
                        )
                    else:
                        self.assertLessEqual(
                            logs[i].get('created_at', ''),
                            logs[i+1].get('created_at', ''),
                            "升序排列验证失败"
                        )
            print(f"[DECORATIVE] 按时间 {direction} 排序成功")
    
    def test_07_pagination(self):
        """测试分页功能"""
        page_size = 10
        
        # 第一页
        response1 = requests.get(
            f'{BASE_URL}/api/v1/audit/logs',
            headers=self.headers,
            params={'page': 1, 'page_size': page_size}
        )
        data1 = response1.json()
        self.assertTrue(data1.get('success'))
        
        # 第二页
        response2 = requests.get(
            f'{BASE_URL}/api/v1/audit/logs',
            headers=self.headers,
            params={'page': 2, 'page_size': page_size}
        )
        data2 = response2.json()
        self.assertTrue(data2.get('success'))
        
        # 验证数据不重复
        if data1.get('data') and data2.get('data'):
            ids1 = {log.get('id') for log in data1.get('data', [])}
            ids2 = {log.get('id') for log in data2.get('data', [])}
            self.assertEqual(len(ids1 & ids2), 0, "分页数据重复")
        print(f"[DECORATIVE] 分页功能正常")
    
    def test_08_get_audit_log_detail(self):
        """测试查询审计日志详情"""
        # 先获取一条日志ID
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/logs',
            headers=self.headers,
            params={'page': 1, 'page_size': 1}
        )
        data = response.json()
        
        if not data.get('data'):
            print("[WARNING] 没有审计日志数据，跳过详情测试")
            return
        
        log_id = data['data'][0]['id']
        
        # 查询详情
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/logs/{log_id}',
            headers=self.headers
        )
        detail = response.json()
        
        self.assertTrue(detail.get('success'))
        self.assertIn('data', detail)
        self.assertEqual(detail['data']['id'], log_id)
        print(f"[DECORATIVE] 查询审计日志详情成功")
    
    def test_09_get_failed_logs(self):
        """测试查询失败日志"""
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/failed',
            headers=self.headers
        )
        data = response.json()
        
        self.assertTrue(data.get('success'))
        self.assertIn('data', data)
        print(f"[DECORATIVE] 查询失败日志成功，共 {len(data.get('data', []))} 条")
    
    def test_10_get_audit_stats(self):
        """测试审计统计"""
        response = requests.get(
            f'{BASE_URL}/api/v1/audit/overview',
            headers=self.headers
        )
        data = response.json()
        
        self.assertTrue(data.get('success'))
        self.assertIn('data', data)
        
        stats = data['data']
        self.assertIn('total', stats)
        self.assertIn('failed', stats)
        self.assertIn('by_action', stats)
        self.assertIn('by_object', stats)
        self.assertIn('by_user', stats)
        print(f"[DECORATIVE] 审计统计查询成功，总计 {stats.get('total')} 条记录")


class TestUserAuditLog(unittest.TestCase):
    """用户审计日志集成测试"""
    
    @classmethod
    def setUpClass(cls):
        """测试前登录"""
        response = requests.post(f'{BASE_URL}/api/v1/auth/login', json={
            'username': ADMIN_USERNAME,
            'password': ADMIN_PASSWORD
        })
        data = response.json()
        cls.token = data.get('data', {}).get('token')
        cls.headers = {'Authorization': f'Bearer {cls.token}'}
    
    def test_11_create_user_creates_audit_log(self):
        """测试创建用户会产生审计日志"""
        # 创建测试用户
        timestamp = int(time.time())
        username = f'test_audit_{timestamp}'
        
        response = requests.post(
            f'{BASE_URL}/api/v1/users',
            headers=self.headers,
            json={
                'username': username,
                'password': 'Test123456',
                'display_name': f'测试用户{timestamp}',
                'email': f'{username}@test.com',
                'role_ids': []
            }
        )
        data = response.json()
        
        self.assertTrue(data.get('success'), f"创建用户失败: {data}")
        user_id = data['data']['id']
        
        # 等待异步审计日志写入
        time.sleep(2)
        
        # 查询该用户的审计日志
        response = requests.get(
            f'{BASE_URL}/api/v1/users/{user_id}/logs',
            headers=self.headers
        )
        logs = response.json()
        
        self.assertTrue(logs.get('success'))
        user_logs = logs.get('data', [])
        
        # 验证有CREATE类型的审计日志
        create_logs = [log for log in user_logs if log.get('action') == 'CREATE']
        self.assertGreater(len(create_logs), 0, "没有找到CREATE类型的审计日志")
        print(f"[DECORATIVE] 创建用户产生了 {len(create_logs)} 条审计日志")
    
    def test_12_update_user_creates_audit_log(self):
        """测试更新用户会产生审计日志"""
        # 先创建一个用户
        timestamp = int(time.time())
        username = f'test_update_{timestamp}'
        
        response = requests.post(
            f'{BASE_URL}/api/v1/users',
            headers=self.headers,
            json={
                'username': username,
                'password': 'Test123456',
                'display_name': f'原始名称{timestamp}',
                'email': f'{username}@test.com',
                'role_ids': []
            }
        )
        data = response.json()
        user_id = data['data']['id']
        time.sleep(1)
        
        # 更新用户
        new_name = f'新名称{timestamp}'
        response = requests.put(
            f'{BASE_URL}/api/v1/users/{user_id}',
            headers=self.headers,
            json={'display_name': new_name}
        )
        data = response.json()
        self.assertTrue(data.get('success'), f"更新用户失败: {data}")
        
        # 等待异步审计日志写入
        time.sleep(1)
        
        # 查询该用户的审计日志
        response = requests.get(
            f'{BASE_URL}/api/v1/users/{user_id}/logs',
            headers=self.headers
        )
        logs = response.json()
        
        self.assertTrue(logs.get('success'))
        user_logs = logs.get('data', [])
        
        # 验证有UPDATE类型的审计日志
        update_logs = [log for log in user_logs if log.get('action') == 'UPDATE']
        self.assertGreater(len(update_logs), 0, "没有找到UPDATE类型的审计日志")
        
        # 验证变更的字段
        display_name_logs = [
            log for log in update_logs 
            if log.get('field_name') == 'display_name'
        ]
        self.assertGreater(len(display_name_logs), 0, "没有找到display_name变更记录")
        print(f"[DECORATIVE] 更新用户产生了 {len(update_logs)} 条审计日志")


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("审计日志功能自动化测试")
    print("=" * 60)
    
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestAuditLogAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestUserAuditLog))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    
    if result.failures:
        print("\n失败的测试:")
        for test, traceback in result.failures:
            print(f"  - {test}")
    
    if result.errors:
        print("\n错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}")
    
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_tests()
    exit(0 if success else 1)
